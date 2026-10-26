import io
import time
import zipfile

from fastapi.testclient import TestClient

from localraw.app import create_app
from tests.support import login, upload, wait_job

BASE = "http://127.0.0.1:8765"


def test_full_flow_multiple_inputs_partial_success_and_downloads(api):
    client, app = api
    raw = upload(client)
    broken = upload(client, "broken.CR3", b"bad")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("folder/photo.CR3", b"good")
        archive.writestr("notes.txt", b"skip")
    zipped = upload(client, "holiday.zip", buffer.getvalue())
    response = client.post(
        "/api/v1/jobs",
        json={"upload_ids": [raw, broken, zipped]},
        headers={"Idempotency-Key": "batch-one"},
    )
    assert response.status_code == 202
    identifier = response.json()["id"]
    job = wait_job(client, identifier)
    assert job["state"] == "completed_with_errors"
    assert job["counters"] == {
        "total": 4,
        "succeeded": 2,
        "failed": 1,
        "skipped": 1,
        "cancelled": 0,
        "finished": 4,
    }
    files = client.get(f"/api/v1/jobs/{identifier}/files").json()["items"]
    for item in files:
        result = client.get(f"/api/v1/jobs/{identifier}/results/{item['output_id']}")
        assert result.status_code == (200 if item["state"] == "succeeded" else 404)
        if result.status_code == 200:
            assert (
                result.content.startswith(b"\xff\xd8")
                and "attachment" in result.headers["content-disposition"]
            )
    zipped_result = client.get(f"/api/v1/jobs/{identifier}/archive")
    with zipfile.ZipFile(io.BytesIO(zipped_result.content)) as archive:
        assert archive.namelist() == ["files/photo.jpg", "holiday/folder/photo.jpg"]
        assert archive.testzip() is None
    assert "private" not in client.get(f"/api/v1/jobs/{identifier}/errors").text
    assert client.get(f"/api/v1/jobs/{identifier}/summary").json()["retry_upload_ids"] == [
        raw,
        broken,
        zipped,
    ]
    retry = client.post(
        "/api/v1/jobs",
        json={"upload_ids": [raw, broken, zipped]},
        headers={"Idempotency-Key": "batch-one"},
    )
    assert retry.json()["id"] == identifier
    assert (
        client.post(
            "/api/v1/jobs", json={"upload_ids": [raw]}, headers={"Idempotency-Key": "batch-one"}
        ).status_code
        == 409
    )
    assert client.delete(f"/api/v1/uploads/{raw}").status_code == 409
    with app.state.workspace.downloading(identifier):
        assert client.delete(f"/api/v1/jobs/{identifier}").status_code == 409
    assert client.delete(f"/api/v1/jobs/{identifier}").status_code == 204
    assert client.get(f"/api/v1/jobs/{identifier}").status_code == 404


def test_session_isolation_and_security(api):
    client, app = api
    raw = upload(client)
    identifier = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()["id"]
    other = TestClient(app, base_url=BASE, client=("127.0.0.1", 50001), headers={"Origin": BASE})
    login(other, app)
    assert other.get("/api/v1/jobs").json()["items"] == []
    for path in (
        f"/jobs/{identifier}",
        f"/jobs/{identifier}/files",
        f"/jobs/{identifier}/summary",
        f"/jobs/{identifier}/archive",
        f"/jobs/{identifier}/errors",
    ):
        assert other.get("/api/v1" + path).status_code == 404
    assert other.delete(f"/api/v1/uploads/{raw}").status_code == 404
    assert (
        client.post(
            "/api/v1/jobs", json={"upload_ids": [raw]}, headers={"X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/jobs", json={"upload_ids": [raw]}, headers={"Origin": "https://evil.test"}
        ).status_code
        == 403
    )
    assert client.get("/health", headers={"Host": "evil.test:8765"}).status_code == 403
    assert client.post("/api/v1/uploads", content=b" " * 70000).status_code == 413
    invalid = client.post("/api/v1/jobs", json={"upload_ids": [raw], "settings": {"jpeg_quality": 20}})
    assert invalid.status_code == 422 and invalid.json()["error"]["request_id"]


def test_exact_upload_retry_and_size_limits(api):
    client, app = api
    identifier = client.post("/api/v1/uploads", json={"filename": "x.cr3", "size_bytes": 4}).json()[
        "upload_id"
    ]
    assert client.put(f"/api/v1/uploads/{identifier}/content", content=b"xx").status_code == 422
    assert not list(app.state.workspace.root.rglob("*.part"))
    assert client.put(f"/api/v1/uploads/{identifier}/content", content=b"xxxxx").status_code == 413
    assert client.put(f"/api/v1/uploads/{identifier}/content", content=b"good").status_code == 200
    assert app.state.uploads.path(app.state.uploads.items[identifier]).read_bytes() == b"good"
    assert (
        client.post("/api/v1/uploads", json={"filename": "../../x.cr3", "size_bytes": 1}).status_code
        == 422
    )
    assert (
        client.post("/api/v1/uploads", json={"filename": "x.cr3", "size_bytes": 2**30}).status_code
        == 413
    )


def test_cancellation_worker_crash_and_timeout(api):
    client, app = api
    app.state.settings.cancel_grace_seconds = 0.05
    hang = upload(client, "slow.cr3", b"hang")
    identifier = client.post("/api/v1/jobs", json={"upload_ids": [hang]}).json()["id"]
    wait_job(client, identifier, terminal=False)
    assert client.post(f"/api/v1/jobs/{identifier}/cancel").status_code == 200
    assert wait_job(client, identifier)["state"] == "cancelled"
    assert client.post(f"/api/v1/jobs/{identifier}/cancel").json()["state"] == "cancelled"
    crash = upload(client, "crash.cr3", b"crash")
    next_id = client.post("/api/v1/jobs", json={"upload_ids": [crash]}).json()["id"]
    assert wait_job(client, next_id)["counters"]["failed"] == 1
    app.state.settings.file_timeout_seconds = 0.3
    timed = client.post("/api/v1/jobs", json={"upload_ids": [hang]}).json()["id"]
    assert wait_job(client, timed)["state"] == "failed"
    assert "timed out" in client.get(f"/api/v1/jobs/{timed}/errors").text
    assert client.get("/health").status_code == 200


def test_restart_recovery_and_expiry(settings):
    settings.lan = True
    app = create_app(settings, start_scheduler=False)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 50000), headers={"Origin": BASE}) as client:
        login(client, app)
        raw = upload(client)
        identifier = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()["id"]
        cookies = dict(client.cookies)
        (app.state.jobs.directory(app.state.jobs.items[identifier]) / "abandoned.jpg.part").write_bytes(
            b"partial"
        )
    restarted = create_app(settings, start_scheduler=False)
    with TestClient(restarted, base_url=BASE, cookies=cookies, headers={"Origin": BASE}) as client:
        session = client.get("/api/v1/sessions")
        assert session.status_code == 200
        client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
        assert client.get(f"/api/v1/jobs/{identifier}").json()["state"] == "interrupted"
        assert not list(settings.workspace.rglob("*.part"))
        retried = client.post("/api/v1/jobs", json={"upload_ids": [raw]})
        assert retried.status_code == 202
        assert client.delete(f"/api/v1/jobs/{identifier}").status_code == 204
        assert raw in restarted.state.uploads.items
        assert client.delete(f"/api/v1/uploads/{raw}").status_code == 409
        newer = restarted.state.jobs.items[retried.json()["id"]]
        newer["state"], newer["expires_at"] = "cancelled", time.time() - 1
        restarted.state.jobs.cleanup()
        assert raw not in restarted.state.uploads.items


def test_actual_spawn_decoder_rejects_corruption(settings, ample_memory):
    app = create_app(settings)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 50000), headers={"Origin": BASE}) as client:
        login(client, app)
        raw = upload(client, content=b"not a real CR3")
        identifier = client.post("/api/v1/jobs", json={"upload_ids": [raw]}).json()["id"]
        result = wait_job(client, identifier)
        assert result["state"] == "failed"
        assert "corrupt or unsupported" in client.get(f"/api/v1/jobs/{identifier}/errors").text
        assert not list(app.state.workspace.root.rglob("*.jpg"))


def test_multiple_archives_unsafe_input_and_deterministic_collisions(api):
    client, app = api

    def archive(entries):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as output:
            for name, data in entries:
                output.writestr(name, data)
        return buffer.getvalue()

    first = upload(client, "trip.zip", archive([("folder/A.CR3", b"good"), ("folder/a.cr3", b"good")]))
    second = upload(client, "TRIP.ZIP", archive([("nested/b.CR3", b"good")]))
    unsafe = upload(client, "unsafe.zip", archive([("ok.cr3", b"good"), ("../evil.cr3", b"good")]))
    identifier = client.post("/api/v1/jobs", json={"upload_ids": [first, second, unsafe]}).json()["id"]
    job = wait_job(client, identifier)
    assert job["state"] == "completed_with_errors"
    assert job["counters"]["succeeded"] == 3 and job["counters"]["failed"] == 1
    with zipfile.ZipFile(io.BytesIO(client.get(f"/api/v1/jobs/{identifier}/archive").content)) as result:
        assert result.namelist() == ["trip/folder/A.jpg", "trip/folder/a__2.jpg", "TRIP__2/nested/b.jpg"]
