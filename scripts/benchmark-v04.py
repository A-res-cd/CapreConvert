"""Reproducible v0.4 real-codec API/preview benchmark, source or frozen executable."""

import argparse
import importlib.metadata
import importlib.util
import io
import json
import platform
import sys
import tempfile
import time
from pathlib import Path

import psutil
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("memory_benchmark", ROOT / "scripts/benchmark-memory.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


def run_case(app, source, conversion, options):
    identifier = app.upload(source)
    with benchmark.MemorySampler(app.process.pid, app.workspace, 0.1) as sampler:
        started = time.perf_counter()
        response = app.client.post(
            "/api/v1/jobs",
            json={"upload_ids": [identifier], "settings": {"conversion": conversion, "raster": options}},
        )
        response.raise_for_status()
        job_id = response.json()["id"]
        job, timings = app.wait(job_id)
        elapsed = time.perf_counter() - started
    files = app.files(job_id)
    case = {
        "conversion": conversion,
        "source": source.name,
        "source_sha256": benchmark.sha256(source),
        "settings": options,
        "state": job["state"],
        "wall_seconds": elapsed,
        "memory": sampler.result(),
        "files": files,
        **timings,
    }
    if files and files[0]["state"] == "succeeded":
        item = files[0]
        started = time.perf_counter()
        result = app.client.get(f"/api/v1/jobs/{job_id}/results/{item['output_id']}")
        result.raise_for_status()
        with Image.open(io.BytesIO(result.content)) as image:
            image.load()
            case["verified_dimensions"] = image.size
        case["download_seconds"] = time.perf_counter() - started
        case["output_bytes"] = len(result.content)
        case["effective_settings"] = item.get("effective_settings")
    return case


def generate_inputs(photo, directory):
    with Image.open(photo) as image:
        image.thumbnail((2400, 2400))
        for kind in ("JPEG", "PNG", "WEBP"):
            image.save(
                directory / ("photo." + {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}[kind]),
                format=kind,
            )
    with Image.new("RGBA", (1600, 1200), (30, 100, 200, 0)) as image:
        image.paste((200, 30, 80, 170), (200, 200, 1300, 900))
        image.save(directory / "transparent.png")
    with Image.open(photo) as image:
        image.thumbnail((4000, 4000))
        image.save(directory / "large.jpg", format="JPEG")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--large-only", action="store_true")
    parser.add_argument(
        "--photo", type=Path, default=ROOT / "test-results/memory-optimized/real/output.jpg"
    )
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Report exists. Choose a new output path.")
    report = {
        "environment": platform.platform(),
        "python": sys.version,
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("Pillow", "pypdfium2", "pypdf", "python-docx", "psutil")
        },
        "physical_bytes": psutil.virtual_memory().total,
        "cases": [],
        "notes": [
            "One worker and default reserves. Sampling 0.1s; not universal resource requirements.",
            "Private photo derives from provenance-documented CR3; never redistributed.",
        ],
    }
    with tempfile.TemporaryDirectory(prefix="v04-benchmark-", dir=ROOT / "test-results") as temporary:
        directory = Path(temporary)
        # Fixture generation exits before timing/admission so the client does not
        # retain native pixel allocations while measuring the server.
        import multiprocessing

        process = multiprocessing.get_context("spawn").Process(
            target=generate_inputs, args=(args.photo, directory)
        )
        process.start()
        process.join(timeout=60)
        if process.is_alive():
            process.kill()
            process.join()
        if process.exitcode != 0:
            raise RuntimeError("Benchmark fixture generation failed")
        process.close()
        arguments = argparse.Namespace(
            executable=args.executable.resolve() if args.executable else None,
            source_root=ROOT,
            interval=0.1,
            timeout=300,
            stderr_path=ROOT / ".cache/v04-benchmark-server.log",
        )
        with benchmark.Application(arguments, directory / "app") as app:
            for filename, conversion, settings in (
                ()
                if args.large_only
                else (
                    ("photo.jpg", "jpg_to_png", {}),
                    ("photo.png", "png_to_webp", {}),
                    ("photo.webp", "webp_to_jpg", {}),
                    ("photo.jpg", "jpg_to_jpg", {"preset": "smaller"}),
                    ("transparent.png", "png_to_webp", {"webp_lossless": True}),
                    ("transparent.png", "png_to_jpg", {"background": "#ffffff"}),
                )
            ):
                report["cases"].append(run_case(app, directory / filename, conversion, settings))
            report["cases"].append(
                run_case(app, directory / "large.jpg", "jpg_to_jpg", {"max_width": 1600})
            )
            report["document_previews"] = (
                "See preview benchmark report; actual engines verified in integration/frozen smoke."
            )
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "report": str(args.output),
                "cases": len(report["cases"]),
                "states": [case["state"] for case in report["cases"]],
            }
        )
    )


if __name__ == "__main__":
    main()
