"""API format tests with a named decoder double, not real camera compatibility proof."""

from contextlib import closing
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from PIL import Image

from localraw.app import create_app
from tests.support import login, upload, wait_job


def png_decoder_double_worker(*args):
    from localraw import conversion
    from localraw.worker import run_worker
    from tests.unit.test_conversion import FakeRaw

    conversion.rawpy.RawPy = FakeRaw
    run_worker(*args)


def test_png_api_download_selection_zip_and_paths(api):
    client, app = api
    app.state.jobs.worker_target = png_decoder_double_worker
    identifier = upload(client)
    job = client.post(
        "/api/v1/jobs", json={"upload_ids": [identifier], "settings": {"conversion": "cr3_to_png"}}
    ).json()
    assert wait_job(client, job["id"])["state"] == "completed"
    item = client.get(f"/api/v1/jobs/{job['id']}/files").json()["items"][0]
    assert item["output_name"].endswith(".png") and item["media_type"] == "image/png"
    result = client.get(f"/api/v1/jobs/{job['id']}/results/{item['output_id']}")
    assert result.headers["content-type"] == "image/png"
    with closing(Image.open(BytesIO(result.content))) as image:
        assert image.format == "PNG" and image.size == (8, 6)
    assert (
        client.get(f"/api/v1/jobs/{job['id']}/previews/{item['output_id']}").headers["content-type"]
        == "image/jpeg"
    )
    selected = client.post(
        f"/api/v1/jobs/{job['id']}/exports", json={"output_ids": [item["output_id"]]}
    ).json()
    zipped = client.get(f"/api/v1/jobs/{job['id']}/exports/{selected['export_id']}")
    with ZipFile(BytesIO(zipped.content)) as archive:
        assert archive.namelist() == [item["output_name"]]
        assert archive.read(item["output_name"]) == result.content
    assert app.state.jobs.output_path(app.state.jobs.items[job["id"]], item).suffix == ".png"


def test_mismatched_document_inputs_reject_before_scheduling(api):
    client, app = api
    document = upload(client, name="text.pdf", content=b"not actually a PDF")
    response = client.post("/api/v1/jobs", json={"upload_ids": [document]})
    assert response.status_code == 422 and response.json()["error"]["code"] == "INPUT_FORMAT_MISMATCH"
    assert not app.state.jobs.items


def test_raw_inputs_cannot_enter_document_engines(api):
    client, app = api
    raw = upload(client)
    response = client.post(
        "/api/v1/jobs", json={"upload_ids": [raw], "settings": {"conversion": "pdf_to_docx"}}
    )
    assert response.status_code == 422


def test_png_workspace_restores_results_preview_and_session(settings, ample_memory):
    base = "http://127.0.0.1:8765"
    app = create_app(settings, worker_target=png_decoder_double_worker)
    with TestClient(app, base_url=base, client=("127.0.0.1", 40000), headers={"Origin": base}) as client:
        login(client, app)
        raw = upload(client)
        job = client.post(
            "/api/v1/jobs", json={"upload_ids": [raw], "settings": {"conversion": "cr3_to_png"}}
        ).json()
        assert wait_job(client, job["id"])["state"] == "completed"
        item = client.get(f"/api/v1/jobs/{job['id']}/files").json()["items"][0]
        route = f"/api/v1/jobs/{job['id']}/results/{item['output_id']}"
        expected = client.get(route).content
        cookies = dict(client.cookies)
    restored = create_app(settings, start_scheduler=False)
    with TestClient(restored, base_url=base, client=("127.0.0.1", 40000), cookies=cookies) as client:
        assert client.get("/api/v1/sessions").status_code == 200
        assert client.get(route).headers["content-type"] == "image/png"
        assert client.get(route).content == expected
        assert client.get(f"/api/v1/jobs/{job['id']}/previews/{item['output_id']}").status_code == 200
        assert client.get(f"/api/v1/jobs/{job['id']}/archive").status_code == 200
