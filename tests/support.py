"""Spawn-safe deterministic worker double, not CR3 conversion evidence."""

import hashlib
import os
import time
from pathlib import Path


def controlled_worker(source, destination, settings, limits, connection, stop):
    content = Path(source).read_bytes()
    if content == b"crash":
        os._exit(17)
    if content == b"hang":
        time.sleep(60)
        return
    connection.send({"stage": "decoding"})
    connection.send({"pixels": 48})
    if not connection.recv()["admitted"]:
        connection.close()
        return
    if content == b"bad":
        connection.send({"error": "Deterministic invalid-image double."})
    else:
        from PIL import Image

        from localraw.conversion import create_previews

        connection.send({"stage": "encoding"})
        image = Image.new("RGB", (8, 6), (88, 133, 100))
        image.save(destination, format="JPEG")
        connection.send({"stage": "validating"})
        connection.send(
            {
                "result": {
                    "width": 8,
                    "height": 6,
                    "size_bytes": Path(destination).stat().st_size,
                    "sha256": hashlib.sha256(Path(destination).read_bytes()).hexdigest(),
                    "warnings": ["Deterministic test double; not RAW decoding."],
                    "preview": create_previews(Path(destination)),
                }
            }
        )
    connection.close()


def oversized_dimensions_worker(source, destination, settings, limits, connection, stop):
    connection.send({"stage": "decoding"})
    connection.send({"pixels": 120_000_000})
    connection.recv()
    connection.close()


def wait_job(client, identifier, terminal=True, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{identifier}").json()
        if job["state"] in {"completed", "completed_with_errors", "cancelled", "failed", "interrupted"}:
            return job
        if not terminal and job["active_files"]:
            return job
        time.sleep(0.05)
    raise AssertionError(f"Job did not reach expected state: {job}")


def login(client, app):
    credential = app.state.security.pairing or app.state.security.bootstrap
    result = client.post("/api/v1/sessions", json={"credential": credential})
    assert result.status_code == 200, result.text
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    return result


def upload(client, name="photo.CR3", content=b"good"):
    response = client.post("/api/v1/uploads", json={"filename": name, "size_bytes": len(content)})
    assert response.status_code == 201, response.text
    identifier = response.json()["upload_id"]
    result = client.put(f"/api/v1/uploads/{identifier}/content", content=content)
    assert result.status_code == 200, result.text
    return identifier
