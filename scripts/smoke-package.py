"""Exercise a frozen build with Python removed from its PATH; never print credentials."""

import argparse
import hashlib
import io
import json
import os
import queue
import re
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "test-results"


def minimal_pdf(text):
    """One real searchable PDF page, generated locally without a fixture dependency."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 16 Tf 72 720 Td ({escaped}) Tj ET\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode("ascii") + b" >>\nstream\n" + content + b"endstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode("ascii") + value + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    return bytes(data)


def windows_resources(executable, release, app_name):
    """Inspect PE resources without executing resource code or accepting default icons."""
    if os.name != "nt":
        return {"status": "not applicable"}
    import pefile

    with pefile.PE(str(executable)) as binary:
        strings = {}
        for entries in binary.FileInfo:
            for entry in entries:
                if entry.Key == b"StringFileInfo":
                    for table in entry.StringTable:
                        strings.update(
                            {
                                key.decode("utf-8"): value.decode("utf-8")
                                for key, value in table.entries.items()
                            }
                        )
        for name in ("ProductName", "FileDescription", "InternalName"):
            assert strings[name] == app_name, f"Incorrect Windows {name}."
        assert strings["FileVersion"] == strings["ProductVersion"] == release.version
        assert strings["OriginalFilename"] == release.executable
        numeric = tuple(map(int, re.match(r"(\d+)\.(\d+)\.(\d+)", release.version).groups())) + (0,)
        fixed = binary.VS_FIXEDFILEINFO[0]
        actual = (
            fixed.FileVersionMS >> 16,
            fixed.FileVersionMS & 65535,
            fixed.FileVersionLS >> 16,
            fixed.FileVersionLS & 65535,
        )
        assert actual == numeric
        types = {entry.id: entry for entry in binary.DIRECTORY_ENTRY_RESOURCE.entries}
        assert {3, 14, 16} <= types.keys(), "Windows icon/group/version resources missing."
        embedded = set()
        for entry in types[3].directory.entries:
            for language in entry.directory.entries:
                record = language.data.struct
                embedded.add(
                    hashlib.sha256(binary.get_data(record.OffsetToData, record.Size)).hexdigest()
                )
    source = (ROOT / "packaging" / "assets" / "capreconvert.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", source)
    assert reserved == 0 and kind == 1
    original = set()
    for index in range(count):
        *_, size, offset = struct.unpack_from("<BBBBHHII", source, 6 + 16 * index)
        original.add(hashlib.sha256(source[offset : offset + size]).hexdigest())
    assert embedded == original, "Windows executable does not embed the current original CC icon."
    return {"status": "passed", "product": app_name, "version": release.version, "icon_frames": count}


def upload_and_run(client, filename, content, conversion):
    registered = client.post("/api/v1/uploads", json={"filename": filename, "size_bytes": len(content)})
    assert registered.status_code == 201, registered.text
    upload_id = registered.json()["upload_id"]
    response = client.put(f"/api/v1/uploads/{upload_id}/content", content=content)
    assert response.status_code == 200, response.text
    created = client.post(
        "/api/v1/jobs", json={"upload_ids": [upload_id], "settings": {"conversion": conversion}}
    )
    assert created.status_code == 202, created.text
    job_id = created.json()["id"]
    # Permit the existing 300-second production worker timeout plus supervision.
    deadline = time.monotonic() + 330
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["state"] in {"completed", "completed_with_errors", "failed", "cancelled"}:
            return job_id, job
        time.sleep(0.1)
    raise AssertionError("Packaged conversion did not finish within the smoke timeout.")


def document_smoke(client, conversions):
    expected = "CapreConvert packaged PDF smoke"
    assert conversions["pdf_to_docx"]["available"]
    job_id, job = upload_and_run(client, "text.pdf", minimal_pdf(expected), "pdf_to_docx")
    assert job["state"] == "completed", client.get(f"/api/v1/jobs/{job_id}/errors").text
    file = client.get(f"/api/v1/jobs/{job_id}/files").json()["items"][0]
    response = client.get(f"/api/v1/jobs/{job_id}/results/{file['output_id']}")
    assert response.status_code == 200 and file["output_name"].endswith(".docx")
    converted_docx = response.content
    with zipfile.ZipFile(io.BytesIO(converted_docx)) as archive:
        assert archive.testzip() is None
        assert expected.encode() in archive.read("word/document.xml")
    preview = client.get(f"/api/v1/jobs/{job_id}/output-preview/{file['output_id']}")
    assert preview.status_code == 200 and preview.json()["kind"] == "docx", preview.text
    assert any(expected in block.get("text", "") for block in preview.json()["blocks"])
    assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 204
    result = {"pdf_to_docx": "passed", "docx_to_pdf": "unavailable: external LibreOffice not detected"}
    if conversions["docx_to_pdf"]["available"]:
        from pypdf import PdfReader

        job_id, job = upload_and_run(client, "text.docx", converted_docx, "docx_to_pdf")
        assert job["state"] == "completed", client.get(f"/api/v1/jobs/{job_id}/errors").text
        file = client.get(f"/api/v1/jobs/{job_id}/files").json()["items"][0]
        response = client.get(f"/api/v1/jobs/{job_id}/results/{file['output_id']}")
        assert response.status_code == 200 and file["output_name"].endswith(".pdf")
        reader = PdfReader(io.BytesIO(response.content))
        assert reader.pages and expected in "\n".join(page.extract_text() or "" for page in reader.pages)
        preview = client.get(f"/api/v1/jobs/{job_id}/output-preview/{file['output_id']}")
        assert preview.status_code == 200 and preview.headers["content-type"] == "image/png", (
            preview.text
        )
        assert preview.headers["x-preview-pages"] == "1"
        assert (
            client.get(f"/api/v1/jobs/{job_id}/output-preview/{file['output_id']}").headers[
                "x-preview-cached"
            ]
            == "true"
        )
        assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 204
        result["docx_to_pdf"] = "passed with external LibreOffice"
    return result


def raster_smoke(client, conversions):
    from PIL import Image

    result = {}
    for key, descriptor in conversions.items():
        if descriptor["engine"] != "raster":
            continue
        source, target = key.split("_to_")
        encoded = io.BytesIO()
        with Image.new(
            "RGB" if source == "jpg" else "RGBA",
            (60, 40),
            (20, 70, 120) if source == "jpg" else (20, 70, 120, 80),
        ) as image:
            image.save(encoded, format={"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[source])
        job_id, job = upload_and_run(client, "photo." + source, encoded.getvalue(), key)
        assert job["state"] == "completed", client.get(f"/api/v1/jobs/{job_id}/errors").text
        item = client.get(f"/api/v1/jobs/{job_id}/files").json()["items"][0]
        response = client.get(f"/api/v1/jobs/{job_id}/results/{item['output_id']}")
        assert response.headers["content-type"] == descriptor["media_type"]
        assert int(response.headers["content-length"]) == len(response.content)
        assert not response.content.startswith(b"PK")
        with Image.open(io.BytesIO(response.content)) as image:
            image.load()
            assert image.size == (60, 40)
            assert image.format == {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[target]
        preview = client.get(f"/api/v1/jobs/{job_id}/previews/{item['output_id']}")
        assert preview.status_code == 200 and preview.headers["content-type"] == "image/png"
        with Image.open(io.BytesIO(preview.content)) as image:
            image.load()
        selected = client.post(
            f"/api/v1/jobs/{job_id}/exports", json={"output_ids": [item["output_id"]]}
        ).json()
        with zipfile.ZipFile(
            io.BytesIO(client.get(f"/api/v1/jobs/{job_id}/exports/{selected['export_id']}").content)
        ) as archive:
            assert archive.read(item["output_name"]) == response.content
        assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 204
        result[key] = "actual codec/direct bytes/preview/ZIP passed"
    return result


def main():
    sys.path.insert(0, str(ROOT))
    from localraw import APP_NAME
    from localraw.packaging import package_names

    release = package_names()
    parser = argparse.ArgumentParser(description=f"Smoke-test an existing {APP_NAME} one-folder build")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist" / release.tag)
    parser.add_argument("--libreoffice", type=Path, help="Explicit external engine for validation only")
    parser.add_argument(
        "--memory-profile",
        choices=("default", "compact"),
        default="default",
        help="Compact caps document workers at384MiB and previews at256MiB for tiny smoke fixtures; reserves remain unchanged",
    )
    arguments = parser.parse_args()
    bundle = arguments.dist_dir.resolve()
    if (bundle / "release.json").is_file():
        metadata = json.loads((bundle / "release.json").read_text("utf-8"))
        assert metadata["application"] == APP_NAME
        filename = metadata["executable"]
        assert Path(filename).name == filename, "Invalid release executable name."
        executable = bundle / filename
    else:
        candidates = [
            path
            for pattern in ("CapreConvert*", "LocalRAW*")
            for path in bundle.glob(pattern + (".exe" if os.name == "nt" else ""))
            if path.is_file()
        ]
        assert len(candidates) == 1, (
            "Expected one application executable. Build the target distribution first."
        )
        executable = candidates[0]
    assert executable.is_file() and executable.resolve().parent == bundle, "Invalid release executable."
    pe_resources = windows_resources(executable, release, APP_NAME)
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-smoke-", dir=ARTIFACTS) as directory:
        assert Path(directory).resolve().is_relative_to(ARTIFACTS.resolve())
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        environment = dict(os.environ)
        for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            environment.pop(name, None)
        if os.name == "nt":
            system_root = environment.get("SYSTEMROOT", environment.get("SystemRoot", "C:\\Windows"))
            environment["PATH"] = str(Path(system_root) / "System32")
        for name in list(environment):
            if name.startswith("LOCALRAW_"):
                del environment[name]
        if arguments.libreoffice:
            engine = arguments.libreoffice.expanduser().resolve()
            assert engine.is_file(), "Configured external LibreOffice executable is missing."
            environment["LOCALRAW_LIBREOFFICE"] = json.dumps(str(engine))
        if arguments.memory_profile == "compact":
            environment["LOCALRAW_DOCUMENT_MEMORY_BYTES"] = str(384 * 1024**2)
            environment["LOCALRAW_PREVIEW_MEMORY_BYTES"] = str(256 * 1024**2)
        process = subprocess.Popen(
            [
                str(executable),
                "--no-browser",
                "--port",
                str(port),
                "--workspace",
                str(Path(directory) / "workspace"),
            ],
            env=environment,
            cwd=directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        tokens = queue.Queue()

        def read_console():
            for line in process.stdout:
                match = re.search(r"#bootstrap=([A-Za-z0-9_-]+)", line)
                if match:
                    tokens.put(match.group(1))

        reader = threading.Thread(target=read_console, daemon=True)
        reader.start()
        try:
            credential = tokens.get(timeout=30)
            base = f"http://127.0.0.1:{port}"
            with httpx.Client(
                base_url=base, headers={"Origin": base}, timeout=10, trust_env=False
            ) as client:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        assert client.get("/health").json() == {"status": "ok"}
                        break
                    except httpx.ConnectError:
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(0.05)
                assert client.get("/api/v1/capabilities").status_code == 401
                assert client.get("/api/v1/resources").status_code == 401
                session = client.post("/api/v1/sessions", json={"credential": credential})
                assert session.status_code == 200
                client.headers["X-CSRF-Token"] = session.json()["csrf_token"]
                caps = client.get("/api/v1/capabilities").json()
                assert caps["application_name"] == APP_NAME
                assert caps["application_version"] == release.version, (
                    "Packaged version does not match source."
                )
                assert caps["rawpy_version"] and caps["libraw_version"] and caps["pillow_version"]
                conversions = {item["id"]: item for item in caps["conversions"]}
                from localraw.formats import CONVERSIONS

                assert set(conversions) == set(CONVERSIONS)
                assert conversions["cr3_to_jpg"]["available"] and conversions["cr3_to_png"]["available"]
                assert "libreoffice" not in caps["limits"], (
                    "Public capabilities expose a local engine path."
                )
                memory = client.get("/api/v1/resources").json()
                assert memory["diagnostics_available"] and memory["application_rss_bytes"] > 0
                assert memory["safety_reserve_bytes"] == caps["limits"]["memory_reserve_bytes"]
                assert (
                    client.get("/api/v1/jobs/missing/previews/missing").json()["error"]["code"]
                    == "JOB_NOT_FOUND"
                )
                assert (
                    client.post("/api/v1/jobs/missing/exports", json={"output_ids": ["missing"]}).json()[
                        "error"
                    ]["code"]
                    == "JOB_NOT_FOUND"
                )
                for resource in (
                    "/",
                    "/static/app.js",
                    "/static/api.js",
                    "/static/styles.css",
                    "/static/assets/mark.svg",
                ):
                    assert client.get(resource).status_code == 200, resource
                for asset in (ROOT / "localraw" / "static").rglob("*"):
                    if asset.is_file():
                        relative = asset.relative_to(ROOT / "localraw" / "static").as_posix()
                        assert client.get("/static/" + relative).content == asset.read_bytes(), (
                            "Packaged static assets are stale. Rebuild."
                        )
                documents = document_smoke(client, conversions)
                rasters = raster_smoke(client, conversions)
                job_id, job = upload_and_run(client, "corrupt.cr3", b"invalid", "cr3_to_png")
                assert job["state"] == "failed"
                errors = client.get(f"/api/v1/jobs/{job_id}/errors").json()
                message = errors["items"][0]["error"]
                assert "memory" in message.lower() or "corrupt or unsupported" in message
                assert client.get(f"/api/v1/jobs/{job_id}/archive").status_code == 409
                assert client.post(f"/api/v1/jobs/{job_id}/cancel").status_code == 200
                assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 204
                result = {
                    "status": "passed",
                    "memory_profile": arguments.memory_profile,
                    "document_memory_bytes": caps["limits"]["document_memory_bytes"],
                    "preview_memory_bytes": caps["limits"]["preview_memory_bytes"],
                    "memory_reserve_bytes": caps["limits"]["memory_reserve_bytes"],
                    "executable": executable.name,
                    "application": caps["application_version"],
                    "application_name": caps["application_name"],
                    "rawpy": caps["rawpy_version"],
                    "libraw": caps["libraw_version"],
                    "pillow": caps["pillow_version"],
                    "invalid_input_result": message,
                    "windows_resources": pe_resources,
                    "documents": documents,
                    "rasters": rasters,
                    "raw_png_invalid_input": "passed",
                    "python_removed_from_child_path": os.name == "nt",
                    "real_camera_conversion": "not exercised here; run the CR3 memory benchmark separately",
                }
                (ARTIFACTS / "package-smoke.json").write_text(
                    json.dumps(result, indent=2), encoding="utf-8"
                )
                print(json.dumps(result, indent=2))
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            reader.join(timeout=2)
            process.stdout.close()


if __name__ == "__main__":
    main()
