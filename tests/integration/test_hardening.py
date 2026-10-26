import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from fastapi.testclient import TestClient

from localraw.app import create_app
from localraw.config import GiB, MiB
from tests.integration.test_api import BASE
from tests.support import login, oversized_dimensions_worker, upload, wait_job


def test_memory_admission_and_dimension_budget(api, monkeypatch):
    client, app = api
    raw = upload(client)
    monkeypatch.setattr(
        "localraw.jobs.psutil.virtual_memory", lambda: SimpleNamespace(available=512 * MiB)
    )
    job = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()
    assert wait_job(client, job["id"])["state"] == "failed"
    assert "Not enough available memory" in client.get(f"/api/v1/jobs/{job['id']}/errors").text
    monkeypatch.setattr(
        "localraw.jobs.psutil.virtual_memory", lambda: SimpleNamespace(available=4 * GiB)
    )
    app.state.jobs.worker_target = oversized_dimensions_worker
    job = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()
    assert wait_job(client, job["id"])["state"] == "failed"
    assert "full-resolution" in client.get(f"/api/v1/jobs/{job['id']}/errors").text
    assert not list(app.state.workspace.root.rglob("*.jpg"))


def test_rss_limit_terminates_worker(api, monkeypatch):
    client, app = api
    raw = upload(client, content=b"hang")
    monkeypatch.setattr("localraw.jobs.worker_rss", lambda pid: 2 * GiB)
    job = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()
    assert wait_job(client, job["id"])["state"] == "failed"
    assert "memory budget" in client.get(f"/api/v1/jobs/{job['id']}/errors").text


def test_capacity_and_cleanup(api, monkeypatch):
    client, app = api
    raw = upload(client)
    item = app.state.uploads.items[raw]
    item["expires_at"] = time.time() - 1
    app.state.uploads.cleanup()
    assert not app.state.uploads.path(item).exists()
    assert raw not in app.state.uploads.items
    quota = app.state.settings.workspace_quota_bytes
    app.state.settings.workspace_quota_bytes = app.state.workspace.used_bytes() + 32
    response = client.post("/api/v1/uploads", json={"filename": "x.cr3", "size_bytes": 1024})
    assert response.status_code == 507
    assert not app.state.workspace.reservations
    app.state.settings.workspace_quota_bytes = quota
    monkeypatch.setattr("localraw.storage.shutil.disk_usage", lambda _: SimpleNamespace(free=0))
    response = client.post("/api/v1/uploads", json={"filename": "x.cr3", "size_bytes": 1024})
    assert response.status_code == 507 and response.json()["error"]["code"] == "INSUFFICIENT_DISK_SPACE"


def test_pairing_rate_limit_and_malformed_security_inputs(api):
    client, app = api
    assert client.post("/api/v1/sessions", json={"credential": "非ASCII"}).status_code == 401
    for host in ("[", "127.0.0.1:8765/evil", "127.0.0.1:8765@evil.test", "127.0.0.1:9999"):
        assert client.get("/health", headers={"Host": host}).status_code == 403
    statuses = [
        client.post("/api/v1/sessions", json={"credential": "wrong"}).status_code for _ in range(10)
    ]
    assert 401 in statuses and statuses[-1] == 429


def test_loopback_bootstrap_is_single_use_and_remote_rejected(settings):
    app = create_app(settings, start_scheduler=False)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 40000), headers={"Origin": BASE}) as local:
        token = app.state.security.bootstrap
        remote = TestClient(app, base_url=BASE, client=("192.168.1.80", 50000), headers={"Origin": BASE})
        assert remote.post("/api/v1/sessions", json={"credential": token}).status_code == 401
        assert remote.get("/api/v1/jobs").status_code == 401
        response = local.post("/api/v1/sessions", json={"credential": token})
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert local.post("/api/v1/sessions", json={"credential": token}).status_code == 401
        assert local.get("/health").json() == {"status": "ok"}


def test_queue_limit_and_atomic_idempotency(settings):
    settings.lan = True
    settings.global_pending_jobs = 1
    app = create_app(settings, start_scheduler=False)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 40000), headers={"Origin": BASE}) as client:
        login(client, app)
        raw = upload(client)

        def submit(_):
            return client.post(
                "/api/v1/jobs", json={"upload_ids": [raw]}, headers={"Idempotency-Key": "same"}
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        assert all(result.status_code == 202 for result in results)
        assert results[0].json()["id"] == results[1].json()["id"]
        assert len(app.state.jobs.items) == 1
        assert client.post("/api/v1/jobs", json={"upload_ids": [raw]}).status_code == 429
        assert len(app.state.uploads.items[raw]["refs"]) == 1


def test_retained_output_integrity_is_checked_on_restart(settings, ample_memory):
    from tests.support import controlled_worker

    settings.lan = True
    app = create_app(settings, worker_target=controlled_worker)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 40000), headers={"Origin": BASE}) as client:
        login(client, app)
        raw = upload(client)
        identifier = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()["id"]
        assert wait_job(client, identifier)["state"] == "completed"
        job = app.state.jobs.items[identifier]
        output_id = job["files"][0]["output_id"]
        app.state.jobs.output_path(job, job["files"][0]).write_bytes(b"damaged")
        cookies = dict(client.cookies)
    app = create_app(settings, start_scheduler=False)
    with TestClient(app, base_url=BASE, cookies=cookies) as client:
        assert client.get(f"/api/v1/jobs/{identifier}").json()["counters"]["failed"] == 1
        assert client.get(f"/api/v1/jobs/{identifier}/results/{output_id}").status_code == 404
        assert client.get(f"/api/v1/jobs/{identifier}/archive").status_code == 409
