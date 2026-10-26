"""Resource-policy tests use explicit doubles; these are not CR3 measurements."""

import time
from pathlib import Path
from types import SimpleNamespace

from localraw.config import GiB, MiB
from tests.support import upload, wait_job


def sized_worker(source, destination, settings, limits, connection, stop):
    from PIL import Image

    # Advertise representative dimensions, but allocate only a tiny test JPEG.
    connection.send({"pixels": 20_438_912})
    if not connection.recv()["admitted"]:
        connection.close()
        return
    connection.send({"stage": "encoding"})
    if stop.wait(1.2):
        connection.close()
        return
    image = Image.new("RGB", (8, 6))
    try:
        image.save(destination, format="JPEG")
    finally:
        image.close()
    connection.send({"stage": "validating"})
    connection.send(
        {"result": {"width": 8, "height": 6, "size_bytes": Path(destination).stat().st_size}}
    )
    connection.close()


def test_representative_dimension_budget_admits_below_old_fixed_floor(api, monkeypatch):
    client, app = api
    app.state.jobs.worker_target = sized_worker
    monkeypatch.setattr(
        "localraw.jobs.psutil.virtual_memory", lambda: SimpleNamespace(available=int(2.5 * GiB))
    )
    raw = upload(client)
    job = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()
    result = wait_job(client, job["id"])
    assert result["state"] == "completed"
    item = client.get(f"/api/v1/jobs/{job['id']}/files").json()["items"][0]
    assert 0 < item["memory"]["peak_rss_bytes"] < item["memory"]["budget_bytes"]


def test_requested_parallelism_falls_back_to_sequential_under_pressure(api, monkeypatch):
    client, app = api
    app.state.jobs.worker_target = sized_worker
    monkeypatch.setattr(
        "localraw.jobs.psutil.virtual_memory", lambda: SimpleNamespace(available=2 * GiB)
    )
    uploads = [upload(client, name=f"sample-{n}.cr3") for n in range(3)]
    job = client.post(
        "/api/v1/jobs", json={"upload_ids": uploads, "settings": {"concurrency": 2}}
    ).json()
    maximum = 0
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        current = client.get(f"/api/v1/jobs/{job['id']}").json()
        maximum = max(maximum, len(current["active_files"]))
        if current["state"] == "completed":
            break
        time.sleep(0.05)
    assert current["state"] == "completed" and current["counters"]["succeeded"] == 3
    assert maximum == 1


def test_sufficient_headroom_still_allows_configured_parallelism(api):
    client, app = api
    app.state.jobs.worker_target = sized_worker
    uploads = [upload(client, name=f"parallel-{n}.cr3") for n in range(2)]
    job = client.post(
        "/api/v1/jobs", json={"upload_ids": uploads, "settings": {"concurrency": 2}}
    ).json()
    maximum = 0
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        current = client.get(f"/api/v1/jobs/{job['id']}").json()
        maximum = max(maximum, len(current["active_files"]))
        if current["state"] == "completed":
            break
        time.sleep(0.05)
    assert current["state"] == "completed" and maximum == 2


def test_runtime_memory_pressure_stops_worker_and_cleans_partial_files(api, monkeypatch):
    client, app = api
    available = SimpleNamespace(available=4 * GiB)
    monkeypatch.setattr("localraw.jobs.psutil.virtual_memory", lambda: available)
    raw = upload(client, content=b"hang")
    job = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()
    wait_job(client, job["id"], terminal=False)
    available.available = 128 * MiB
    result = wait_job(client, job["id"])
    assert result["state"] == "failed"
    assert "Available system memory fell" in client.get(f"/api/v1/jobs/{job['id']}/errors").text
    assert not list(app.state.workspace.root.rglob("*.part"))
    assert not list(app.state.workspace.root.rglob("*.jpg"))
    assert not app.state.workspace.reservations


def test_resources_are_authenticated_and_include_tree_peaks(api):
    client, app = api
    status = client.get("/api/v1/resources").json()
    assert status["application_peak_sampled_rss_bytes"] >= status["application_rss_bytes"] > 0
    assert status["safety_reserve_bytes"] == app.state.settings.memory_reserve_bytes
    assert status["conversion_workers"] == 0
    assert "workspace" not in status and "pid" not in status
    client.cookies.clear()
    assert client.get("/api/v1/resources").status_code == 401
