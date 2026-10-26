"""Benchmark accounting/streaming checks; never camera compatibility evidence."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageCms

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark-memory.py"
SPEC = importlib.util.spec_from_file_location("benchmark_memory", SCRIPT)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def test_manifest_provenance_hash_and_path_bounds(tmp_path):
    source = tmp_path / "private.cr3"
    source.write_bytes(b"test-input-not-a-real-raw")
    manifest = tmp_path / "manifest.json"
    record = {
        "filename": source.name,
        "sha256": benchmark.sha256(source),
        "provenance": "Explicit test double for harness validation only.",
    }
    manifest.write_text(json.dumps([record]), encoding="utf-8")
    assert benchmark.load_inputs(manifest)[0]["path"] == source
    source.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        benchmark.load_inputs(manifest)
    record["filename"] = "../escape.cr3"
    manifest.write_text(json.dumps([record]), encoding="utf-8")
    with pytest.raises(ValueError, match="inside its input directory"):
        benchmark.load_inputs(manifest)
    with pytest.raises(ValueError, match="provenance"):
        benchmark.load_inputs(data_dir=tmp_path)


def test_sampler_tree_worker_lifetime_peak_and_disk_accounting(tmp_path, monkeypatch):
    (tmp_path / "staged.part").write_bytes(b"x" * 1234)

    class Process:
        def __init__(self, pid):
            self.pid = pid

        def children(self, recursive=True):
            return [Process(2)]

        def memory_info(self):
            return SimpleNamespace(rss=100 if self.pid == 1 else 80, peak_wset=200)

        def cmdline(self):
            return ["LocalRAW.exe", "--multiprocessing-fork"]

    monkeypatch.setattr(benchmark.psutil, "Process", Process)
    monkeypatch.setattr(benchmark.psutil, "virtual_memory", lambda: SimpleNamespace(available=900))
    sampler = benchmark.MemorySampler(1, tmp_path)
    sampler.sample()
    report = sampler.result()
    assert report["peak_tree_rss_bytes"] == 180
    assert report["peak_parent_rss_bytes"] == 100
    assert report["peak_children_rss_bytes"] == 80
    assert report["max_conversion_workers"] == 1
    assert report["max_processes_including_server"] == 2
    assert report["peak_workspace_bytes"] == 1234
    assert report["minimum_system_available_bytes"] == 900
    assert report["windows_process_lifetime_peak_working_sets_bytes"] == {"1": 200, "2": 200}


def test_upload_is_streamed_in_bounded_chunks(tmp_path):
    path = tmp_path / "large.cr3"
    with path.open("wb") as stream:
        stream.truncate(benchmark.CHUNK * 3 + 17)
    received = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"upload_id": "opaque"}

    class Client:
        def post(self, route, json):
            assert json["size_bytes"] == path.stat().st_size
            return Response()

        def put(self, route, content, headers):
            assert not isinstance(content, bytes)
            assert headers["Content-Length"] == str(path.stat().st_size)
            received.extend(len(chunk) for chunk in content)
            return Response()

    app = benchmark.Application(SimpleNamespace(), tmp_path)
    app.client = Client()
    assert app.upload(path) == "opaque"
    assert received == [benchmark.CHUNK, benchmark.CHUNK, benchmark.CHUNK, 17]


def test_jpeg_integrity_records_pixel_hash_and_checks_geometry(tmp_path):
    path = tmp_path / "valid.jpg"
    exif = Image.Exif()
    exif[274] = 1
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    with Image.new("RGB", (64, 40), (77, 123, 166)) as image:
        image.save(path, quality=95, subsampling=0, exif=exif, icc_profile=profile)
    checked = benchmark.inspect_jpeg(path, {"width": 64, "height": 40})
    with Image.open(path) as image:
        assert checked["decoded_pixel_sha256"] == hashlib.sha256(image.tobytes()).hexdigest()
    assert checked["dimensions_match_manifest"]
    assert checked["icc_sha256"] == hashlib.sha256(profile).hexdigest()
    with pytest.raises(ValueError, match="dimensions"):
        benchmark.inspect_jpeg(path, {"width": 32, "height": 20})
    with Image.new("RGB", (64, 40), (77, 123, 166)) as image:
        image.save(path, quality=95, subsampling=2, exif=exif, icc_profile=profile)
    with pytest.raises(ValueError, match="chroma sampling"):
        benchmark.inspect_jpeg(path)


def test_benchmark_refuses_report_overwrite_and_fast_polling(tmp_path):
    output = tmp_path / "exists.json"
    output.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        benchmark.parse_arguments(["--output", str(output)])
    with pytest.raises(SystemExit):
        benchmark.parse_arguments(["--interval", "0.001"])
