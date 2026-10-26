"""Optional real camera gate. No synthetic image is accepted as compatibility proof."""

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from localraw.app import create_app
from localraw.storage import file_hash
from tests.support import login, wait_job

ROOT = Path(__file__).parents[1] / "fixtures"
MANIFEST = ROOT / "manifest.json"
CASES = json.loads(MANIFEST.read_text("utf-8")) if MANIFEST.exists() else [None]


@pytest.mark.real
@pytest.mark.parametrize("sample", CASES)
def test_licensed_real_camera_fixture(settings, sample):
    if sample is None:
        pytest.skip("BLOCKED: licensed CR3 fixtures and manifest.json not provided")
    for field in ("filename", "camera", "mode", "provenance", "sha256", "width", "height"):
        assert sample.get(field), f"Missing fixture field: {field}"
    path = (ROOT / sample["filename"]).resolve()
    assert path.is_relative_to(ROOT.resolve()) and path.suffix.lower() == ".cr3"
    assert file_hash(path) == sample["sha256"]
    app = create_app(settings)
    base = f"http://127.0.0.1:{settings.port}"
    with TestClient(app, base_url=base, client=("127.0.0.1", 40000), headers={"Origin": base}) as client:
        login(client, app)
        registered = client.post(
            "/api/v1/uploads", json={"filename": path.name, "size_bytes": path.stat().st_size}
        )
        assert registered.status_code == 201
        upload_id = registered.json()["upload_id"]
        with path.open("rb") as source:
            assert (
                client.put(
                    f"/api/v1/uploads/{upload_id}/content",
                    content=iter(lambda: source.read(1024**2), b""),
                ).status_code
                == 200
            )
        response = client.post("/api/v1/jobs", json={"upload_ids": [upload_id]})
        assert response.status_code == 202
        job_id = response.json()["id"]
        job = wait_job(client, job_id, timeout=settings.file_timeout_seconds + 60)
        assert job["state"] == "completed", client.get(f"/api/v1/jobs/{job_id}/errors").json()
        item = client.get(f"/api/v1/jobs/{job_id}/files").json()["items"][0]
        result = client.get(f"/api/v1/jobs/{job_id}/results/{item['output_id']}")
        with Image.open(io.BytesIO(result.content)) as jpeg:
            jpeg.load()
            assert jpeg.size == (sample["width"], sample["height"])
            assert jpeg.mode == "RGB" and jpeg.getexif()[274] == 1
            assert jpeg.info["icc_profile"]
    assert file_hash(path) == sample["sha256"]
