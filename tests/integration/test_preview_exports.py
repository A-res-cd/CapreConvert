import io
import zipfile

from fastapi.testclient import TestClient
from PIL import Image

from localraw.app import create_app
from tests.integration.test_api import BASE
from tests.support import controlled_worker, login, upload, wait_job


def batch(client, count=3):
    ids = [upload(client, f"photo{index + 1}.cr3") for index in range(count)]
    ids.append(upload(client, "failed.cr3", b"bad"))
    response = client.post("/api/v1/jobs", json={"upload_ids": ids, "settings": {"concurrency": 2}})
    assert response.status_code == 202
    job_id = response.json()["id"]
    wait_job(client, job_id, timeout=40)
    files = client.get(f"/api/v1/jobs/{job_id}/files").json()["items"]
    assert sum(file["state"] == "succeeded" for file in files) == count
    return job_id, files


def test_owned_inline_previews_and_thumbnails(api):
    client, app = api
    job_id, files = batch(client, count=1)
    photo = files[0]
    assert photo["preview"] and photo["preview"]["thumbnail"]
    for query in ("", "?thumbnail=true"):
        response = client.get(f"/api/v1/jobs/{job_id}/previews/{photo['output_id']}" + query)
        assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
        assert response.headers["content-disposition"].startswith("inline")
        with Image.open(io.BytesIO(response.content)) as image:
            image.load()
            assert image.size == (8, 6) and image.getexif()[274] == 1
    failed = files[-1]
    assert client.get(f"/api/v1/jobs/{job_id}/previews/{failed['output_id']}").status_code == 404
    assert not app.state.workspace.downloads


def test_selected_export_contains_only_chosen_full_jpgs_and_reuses_cache(api):
    client, app = api
    job_id, files = batch(client)
    chosen = [files[2]["output_id"], files[0]["output_id"]]
    response = client.post(f"/api/v1/jobs/{job_id}/exports", json={"output_ids": chosen})
    assert response.status_code == 201 and response.json()["count"] == 2
    export_id = response.json()["export_id"]
    repeated = client.post(f"/api/v1/jobs/{job_id}/exports", json={"output_ids": list(reversed(chosen))})
    assert repeated.json()["export_id"] == export_id
    result = client.get(f"/api/v1/jobs/{job_id}/exports/{export_id}")
    assert result.status_code == 200 and "attachment" in result.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert archive.namelist() == ["files/photo1.jpg", "files/photo3.jpg"]
        assert archive.testzip() is None
        for file in (files[0], files[2]):
            full = client.get(f"/api/v1/jobs/{job_id}/results/{file['output_id']}").content
            assert archive.read(file["output_name"]) == full
    assert len(list(app.state.jobs.directory(app.state.jobs.items[job_id]).glob("selection-*.zip"))) == 1
    assert not app.state.workspace.downloads and not app.state.workspace.reservations


def test_export_validation_ownership_and_csrf(api):
    client, app = api
    job_id, files = batch(client, count=1)
    chosen = files[0]["output_id"]
    base = f"/api/v1/jobs/{job_id}"
    for ids, expected in (
        ([], 422),
        ([chosen, chosen], 422),
        ([files[-1]["output_id"]], 404),
        (["unknown"], 404),
    ):
        assert client.post(base + "/exports", json={"output_ids": ids}).status_code == expected
    assert (
        client.post(
            base + "/exports", json={"output_ids": [chosen]}, headers={"X-CSRF-Token": "bad"}
        ).status_code
        == 403
    )
    prepared = client.post(base + "/exports", json={"output_ids": [chosen]}).json()
    other = TestClient(app, base_url=BASE, client=("127.0.0.1", 40001), headers={"Origin": BASE})
    login(other, app)
    assert other.post(base + "/exports", json={"output_ids": [chosen]}).status_code == 404
    assert other.get(base + f"/previews/{chosen}").status_code == 404
    assert other.get(base + f"/exports/{prepared['export_id']}").status_code == 404


def test_export_cache_never_deletes_active_download(api):
    client, app = api
    app.state.settings.export_cache_per_job = 1
    job_id, files = batch(client, count=2)
    base = f"/api/v1/jobs/{job_id}"
    first = client.post(base + "/exports", json={"output_ids": [files[0]["output_id"]]}).json()[
        "export_id"
    ]
    with app.state.workspace.downloading(job_id):
        assert (
            client.post(base + "/exports", json={"output_ids": [files[1]["output_id"]]}).status_code
            == 409
        )
        assert client.get(base + f"/exports/{first}").status_code == 200
        assert client.delete(base).status_code == 409
    newer = client.post(base + "/exports", json={"output_ids": [files[1]["output_id"]]})
    assert newer.status_code == 201 and newer.json()["export_id"] != first
    assert client.get(base + f"/exports/{first}").status_code == 404


def test_export_failure_cleans_partials_and_releases_capacity(api, monkeypatch):
    client, app = api
    job_id, files = batch(client, count=1)
    monkeypatch.setattr(
        "localraw.jobs.package_outputs",
        lambda *args: (_ for _ in ()).throw(ValueError("packaging failure double")),
    )
    result = client.post(f"/api/v1/jobs/{job_id}/exports", json={"output_ids": [files[0]["output_id"]]})
    assert result.status_code == 507
    assert not app.state.workspace.downloads and not app.state.workspace.reservations
    assert not list(app.state.jobs.directory(app.state.jobs.items[job_id]).glob("selection-*.zip*"))
    assert client.get(f"/api/v1/jobs/{job_id}/results/{files[0]['output_id']}").status_code == 200


def test_preview_and_selection_survive_restart_and_damaged_preview_is_isolated(settings, ample_memory):
    settings.lan = True
    app = create_app(settings, worker_target=controlled_worker)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 40000), headers={"Origin": BASE}) as client:
        login(client, app)
        job_id, files = batch(client, count=1)
        output_id = files[0]["output_id"]
        export_id = client.post(
            f"/api/v1/jobs/{job_id}/exports", json={"output_ids": [output_id]}
        ).json()["export_id"]
        cookies = dict(client.cookies)
    for damaged in (False, True):
        if damaged:
            job = app.state.jobs.items[job_id]
            app.state.jobs.preview_path(job, job["files"][0]).write_bytes(b"damaged preview")
        app = create_app(settings, start_scheduler=False)
        with TestClient(app, base_url=BASE, cookies=cookies) as client:
            assert client.get(f"/api/v1/jobs/{job_id}/results/{output_id}").status_code == 200
            assert client.get(f"/api/v1/jobs/{job_id}/exports/{export_id}").status_code == 200
            assert client.get(f"/api/v1/jobs/{job_id}/previews/{output_id}").status_code == (
                404 if damaged else 200
            )
