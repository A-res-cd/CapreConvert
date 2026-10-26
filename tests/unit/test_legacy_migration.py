"""Load representative pre-v0.3 manifests without renaming persisted identities.

The retained input here is a byte fixture, never camera-compatibility evidence.
"""

import hashlib
import json
import time
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from localraw.app import create_app
from localraw.config import Settings, default_workspace
from localraw.security import COOKIE
from localraw.storage import Workspace, atomic_json, file_hash

BASE = "http://127.0.0.1:8765"
LEGACY_SETTINGS = {
    "jpeg_quality": 95,
    "filename_suffix": "",
    "white_balance": "camera",
    "preserve_metadata": True,
    "include_gps": False,
    "concurrency": 1,
}


@pytest.fixture
def legacy_workspace(settings):
    workspace = Workspace(settings).open()
    owner, upload_id, completed_id, interrupted_id = (str(number) * 32 for number in range(1, 5))
    file_id, output_id, export_id = (str(number) * 32 for number in range(5, 8))
    now = time.time()
    retained = b"Legacy retained CR3 input byte fixture; no RAW decoding is performed."
    (workspace.root / "uploads" / (upload_id + ".input")).write_bytes(retained)
    atomic_json(
        workspace.manifest("upload", upload_id),
        {
            "id": upload_id,
            "owner": owner,
            "filename": "legacy.CR3",
            "size_bytes": len(retained),
            "state": "ready",
            "refs": [completed_id, interrupted_id],
            "expires_at": now + 3600,
        },
    )
    directory = workspace.root / "jobs" / completed_id
    directory.mkdir()
    image_path = directory / (output_id + ".jpg")
    with Image.new("RGB", (8, 6), (44, 88, 132)) as image:
        image.save(image_path, format="JPEG", quality=95, subsampling=0)
    derivative = {}
    for kind in ("preview", "thumbnail"):
        path = directory / (output_id + f".{kind}.jpg")
        path.write_bytes(image_path.read_bytes())
        derivative[kind] = {
            "width": 8,
            "height": 6,
            "size_bytes": path.stat().st_size,
            "sha256": file_hash(path),
        }
    for name in ("results.zip", f"selection-{export_id}.zip"):
        with zipfile.ZipFile(directory / name, "w") as archive:
            archive.write(image_path, "files/legacy.jpg")
    file = {
        "id": file_id,
        "upload_id": upload_id,
        "output_id": output_id,
        "name": "legacy.CR3",
        "state": "succeeded",
        "warnings": [],
        "error": None,
        "output_name": "files/legacy.jpg",
        "width": 8,
        "height": 6,
        "size_bytes": image_path.stat().st_size,
        "sha256": file_hash(image_path),
        "preview": {**derivative["preview"], "thumbnail": derivative["thumbnail"]},
    }
    completed = {
        "id": completed_id,
        "owner": owner,
        "state": "completed",
        "files": [file],
        "settings": dict(LEGACY_SETTINGS),
        "upload_ids": [upload_id],
        "created_at": now,
        "expires_at": now + 86400,
        "warnings": [],
        "package_status": "ready",
        "idempotency_key": "legacy-submission",
        "payload_hash": hashlib.sha256(
            json.dumps({"upload_ids": [upload_id], "settings": LEGACY_SETTINGS}, sort_keys=True).encode()
        ).hexdigest(),
        "exports": [
            {
                "id": export_id,
                "fingerprint": hashlib.sha256(json.dumps([output_id]).encode()).hexdigest(),
                "count": 1,
                "size_bytes": (directory / f"selection-{export_id}.zip").stat().st_size,
            }
        ],
    }
    interrupted = {
        **completed,
        "id": interrupted_id,
        "state": "converting",
        "files": [
            {
                **file,
                "id": "8" * 32,
                "output_id": "9" * 32,
                "state": "decoding",
                "preview": None,
            }
        ],
        "idempotency_key": None,
        "payload_hash": "unused",
        "package_status": "pending",
        "exports": [],
    }
    active_directory = workspace.root / "jobs" / interrupted_id
    active_directory.mkdir()
    (active_directory / ("9" * 32 + ".jpg.part")).write_bytes(b"partial JPEG")
    (active_directory / ("8" * 32 + ".cr3")).write_bytes(b"staged temporary RAW")
    for job in (completed, interrupted):
        atomic_json(workspace.manifest("job", job["id"]), job)
    token, csrf = "legacy-browser-token", "legacy-csrf"
    foreign_token = "another-browser-token"
    atomic_json(
        workspace.root / "manifests" / "sessions.json",
        {
            hashlib.sha256(token.encode()).hexdigest(): {
                "owner": owner,
                "csrf": csrf,
                "expires": now + 3600,
            },
            hashlib.sha256(foreign_token.encode()).hexdigest(): {
                "owner": "f" * 32,
                "csrf": "other-csrf",
                "expires": now + 3600,
            },
        },
    )
    expected_files = {path.name: path.read_bytes() for path in directory.iterdir()}
    marker = (workspace.root / ".localraw-workspace").read_bytes()
    workspace.close()
    return {
        "completed_id": completed_id,
        "interrupted_id": interrupted_id,
        "upload_id": upload_id,
        "output_id": output_id,
        "export_id": export_id,
        "token": token,
        "csrf": csrf,
        "foreign_token": foreign_token,
        "retained": retained,
        "files": expected_files,
        "marker": marker,
    }


def test_legacy_workspace_resumes_session_outputs_and_interrupted_work(settings, legacy_workspace):
    old = legacy_workspace
    assert COOKIE == "localraw_session"
    app = create_app(settings, start_scheduler=False)
    with TestClient(
        app, base_url=BASE, cookies={COOKIE: old["token"]}, headers={"Origin": BASE}
    ) as client:
        response = client.get("/api/v1/sessions")
        assert response.status_code == 200
        assert response.json()["csrf_token"] == old["csrf"]
        client.headers["X-CSRF-Token"] = old["csrf"]
        job_url = f"/api/v1/jobs/{old['completed_id']}"
        job = client.get(job_url).json()
        assert job["state"] == "completed" and job["counters"]["succeeded"] == 1
        assert job["settings"] == {**LEGACY_SETTINGS, "conversion": "cr3_to_jpg"}
        assert app.state.jobs.items[old["completed_id"]]["settings"] == LEGACY_SETTINGS
        persisted = json.loads(
            (settings.workspace / "manifests" / f"job-{old['completed_id']}.json").read_text("utf-8")
        )
        assert persisted["settings"] == LEGACY_SETTINGS
        output = client.get(job_url + f"/results/{old['output_id']}")
        assert output.status_code == 200 and output.headers["content-type"] == "image/jpeg"
        assert output.content == old["files"][old["output_id"] + ".jpg"]
        assert client.get(job_url + "/archive").content == old["files"]["results.zip"]
        preview = client.get(job_url + f"/previews/{old['output_id']}")
        thumbnail = client.get(job_url + f"/previews/{old['output_id']}?thumbnail=true")
        assert preview.status_code == thumbnail.status_code == 200
        assert preview.content == old["files"][old["output_id"] + ".preview.jpg"]
        assert thumbnail.content == old["files"][old["output_id"] + ".thumbnail.jpg"]
        selection = client.get(job_url + f"/exports/{old['export_id']}")
        assert selection.content == old["files"][f"selection-{old['export_id']}.zip"]
        interrupted = client.get(f"/api/v1/jobs/{old['interrupted_id']}").json()
        assert interrupted["state"] == "interrupted"
        assert interrupted["counters"]["cancelled"] == 1
        assert not list(settings.workspace.rglob("*.part"))
        assert not list((settings.workspace / "jobs").rglob("*.cr3"))
        assert (settings.workspace / ".localraw-workspace").read_bytes() == old["marker"]
        retained = settings.workspace / "uploads" / (old["upload_id"] + ".input")
        assert retained.read_bytes() == old["retained"]
        with pytest.raises(RuntimeError, match="already in use"):
            with TestClient(create_app(settings, start_scheduler=False), base_url=BASE):
                pass
        assert client.get(job_url).status_code == 200


def test_legacy_submission_idempotency_and_owned_retained_retry(settings, legacy_workspace):
    old = legacy_workspace
    app = create_app(settings, start_scheduler=False)
    with TestClient(
        app,
        base_url=BASE,
        cookies={COOKIE: old["token"]},
        headers={"Origin": BASE, "X-CSRF-Token": old["csrf"]},
    ) as client:
        body = {"upload_ids": [old["upload_id"]], "settings": dict(LEGACY_SETTINGS)}
        repeated = client.post(
            "/api/v1/jobs", json=body, headers={"Idempotency-Key": "legacy-submission"}
        )
        assert repeated.status_code == 202 and repeated.json()["id"] == old["completed_id"]
        body["settings"]["conversion"] = "cr3_to_png"
        conflict = client.post(
            "/api/v1/jobs", json=body, headers={"Idempotency-Key": "legacy-submission"}
        )
        assert conflict.status_code == 409
        retried = client.post("/api/v1/jobs", json={"upload_ids": [old["upload_id"]]})
        assert retried.status_code == 202
        assert retried.json()["settings"]["conversion"] == "cr3_to_jpg"
        client.cookies.set(COOKIE, old["foreign_token"])
        assert client.get(f"/api/v1/jobs/{old['completed_id']}").status_code == 404
        assert (
            client.get(f"/api/v1/jobs/{old['completed_id']}/results/{old['output_id']}").status_code
            == 404
        )


def test_legacy_workspace_location_and_environment_prefix_remain_supported(tmp_path, monkeypatch):
    import os

    for name in list(os.environ):
        if name.startswith("LOCALRAW_"):
            monkeypatch.delenv(name)
    appdata = tmp_path / "application-data"
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))
    assert default_workspace() == appdata / "LocalRAW" / "workspace"
    monkeypatch.setenv("LOCALRAW_PORT", "8877")
    loaded = Settings.load()
    assert loaded.port == 8877
    assert loaded.workspace == (appdata / "LocalRAW" / "workspace").resolve()
