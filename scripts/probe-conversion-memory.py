"""Isolated conversion allocation experiment; never a production admission benchmark.

Only use inputs you own. Reports and outputs stay under the specified new directory.
The normal API guard is deliberately absent here so native costs can be measured;
the supervising process enforces separate physical-memory and process-RSS limits.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
MiB = 1024**2


def memory():
    info = psutil.Process().memory_info()
    return {"rss_bytes": info.rss, "kernel_peak_rss_bytes": getattr(info, "peak_wset", None)}


def disk_bytes(directory):
    total = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except FileNotFoundError:  # Atomic publication may replace a .part between samples.
            pass
    return total


def stop_tree(process):
    try:
        parent = psutil.Process(process.pid)
        for item in reversed([parent, *parent.children(recursive=True)]):
            try:
                item.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass


def child(arguments):
    sys.path.insert(0, str(ROOT))
    import numpy as np
    from PIL import Image

    from localraw.models import ConversionSettings
    from localraw.storage import file_hash

    if arguments.module_file:
        spec = importlib.util.spec_from_file_location(
            "localraw._conversion_probe", arguments.module_file
        )
        conversion = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(conversion)
    else:
        from localraw import conversion

    synthetic = bool(arguments.synthetic)
    if synthetic:
        width, height = map(int, arguments.synthetic.lower().split("x"))

        class ExplicitSyntheticRaw:
            """Exercises transfer/encoding only, never CR3 decoder evidence."""

            sizes = type("Sizes", (), {"width": width, "height": height, "flip": 0})()
            camera_whitebalance = (2.0, 1.0, 1.5, 1.0)

            def __enter__(self):
                return self

            def __exit__(self, *unused):
                pass

            def open_file(self, unused):
                pass

            def unpack(self):
                pass

            def postprocess(self, **unused):
                return np.arange(width * height * 3, dtype=np.uint16).reshape(height, width, 3)

        conversion.rawpy.RawPy = ExplicitSyntheticRaw
    events = []
    started = time.monotonic()

    def progress(stage):
        events.append({"stage": stage, "elapsed_seconds": time.monotonic() - started, **memory()})

    def admit(pixels):
        events.append({"stage": "dimensions", "pixels": pixels, **memory()})

    destination = arguments.output_dir / "output.jpg"
    try:
        result = conversion.convert(
            arguments.source,
            destination,
            ConversionSettings(),
            {"max_pixels": 120_000_000, "min_free_bytes": 512 * MiB},
            progress,
            admit,
        )
        conversion_seconds = time.monotonic() - started
        events.append({"stage": "finished", "elapsed_seconds": conversion_seconds, **memory()})
        # Validate exact exported pixels in bounded strips; do not copy RGB as one bytes object.
        pixels = hashlib.sha256()
        with closing(Image.open(destination)) as image:
            image.load()
            for row in range(0, image.height, 128):
                with closing(image.crop((0, row, image.width, min(row + 128, image.height)))) as strip:
                    pixels.update(strip.tobytes())
            integrity = {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "orientation": image.getexif().get(274),
                "sampling": image.layer,
                "quantization": image.quantization,
                "decoded_rgb_sha256": pixels.hexdigest(),
                "icc_sha256": hashlib.sha256(image.info["icc_profile"]).hexdigest(),
                "jpeg_sha256": file_hash(destination),
            }
        report = {"status": "succeeded", "duration_seconds": conversion_seconds, "result": result}
        report["integrity"] = integrity
    except Exception as exc:
        report = {"status": "failed", "error": str(exc), "duration_seconds": time.monotonic() - started}
    report.update(
        {
            "events": events,
            "final_memory": memory(),
            "conversion_source_sha256": file_hash(Path(conversion.__file__)),
            "input_sha256": None if synthetic else file_hash(arguments.source),
            "settings": ConversionSettings().model_dump(),
            "rawpy_version": conversion.rawpy.__version__,
            "libraw_version": conversion.rawpy.libraw_version,
        }
    )
    (arguments.output_dir / "worker-report.json").write_text(json.dumps(report, indent=2), "utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--synthetic", help="Explicit synthetic transfer probe, e.g. 6000x4000")
    parser.add_argument("--module-file", type=Path, help="Saved pre-change conversion.py for baseline")
    parser.add_argument("--output-dir", type=Path, required=True, help="Must not already exist")
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--worker-cap-mib", type=int, default=1024, help="Experiment RSS cap, 512..1331 MiB"
    )
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args()
    arguments.output_dir = arguments.output_dir.resolve()
    if bool(arguments.source) == bool(arguments.synthetic):
        parser.error("Choose exactly one of --source and --synthetic.")
    if arguments.synthetic:
        try:
            width, height = map(int, arguments.synthetic.lower().split("x"))
            if min(width, height) <= 0 or width * height > 120_000_000:
                raise ValueError()
        except ValueError:
            parser.error("Synthetic size must be WIDTHxHEIGHT within 120 million pixels.")
        arguments.source = Path("explicit-synthetic-not-a-cr3")
    elif not arguments.source.is_file() or arguments.source.suffix.lower() != ".cr3":
        parser.error("Source must be an existing private CR3 input.")
    else:
        arguments.source = arguments.source.resolve()
    if arguments.module_file:
        arguments.module_file = arguments.module_file.resolve()
    if arguments.child:
        child(arguments)
        return
    available = psutil.virtual_memory().available
    if not 512 <= arguments.worker_cap_mib <= 1331:
        parser.error("Experiment worker cap must be between 512 and 1331 MiB.")
    cap = arguments.worker_cap_mib * MiB
    reserve = 768 * MiB
    if available < cap + reserve:
        parser.error("Experiment requires its worker cap plus 768 MiB physical reserve.")
    arguments.output_dir.mkdir(parents=True, exist_ok=False)
    environment = dict(os.environ)
    for variable in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        environment[variable] = "1"
    command = [sys.executable, str(Path(__file__).resolve()), "--child", "--label", arguments.label]
    command.extend(["--output-dir", str(arguments.output_dir)])
    if arguments.synthetic:
        command.extend(["--synthetic", arguments.synthetic])
    else:
        command.extend(["--source", str(arguments.source)])
    if arguments.module_file:
        command.extend(["--module-file", str(arguments.module_file)])
    started = time.monotonic()
    process = subprocess.Popen(command, env=environment, cwd=ROOT)
    sampled_peak = peak_disk = peak_workers = 0
    lowest_available = available
    stopped = None
    try:
        while process.poll() is None:
            try:
                tree = [psutil.Process(process.pid)]
                tree.extend(tree[0].children(recursive=True))
                rss = sum(item.memory_info().rss for item in tree)
                peak_workers = max(peak_workers, len(tree))
                sampled_peak = max(sampled_peak, rss)
                free = psutil.virtual_memory().available
                lowest_available = min(lowest_available, free)
                peak_disk = max(peak_disk, disk_bytes(arguments.output_dir))
                if rss > cap or free < 256 * MiB or time.monotonic() - started > 300:
                    stopped = "Experiment stopped: process RSS, physical reserve or duration limit."
                    stop_tree(process)
                    break
            except psutil.NoSuchProcess:
                pass
            time.sleep(0.05)
    finally:
        if process.poll() is None:
            stop_tree(process)
        process.wait(timeout=10)
    report_path = arguments.output_dir / "worker-report.json"
    worker = json.loads(report_path.read_text("utf-8")) if report_path.is_file() else None
    report = {
        "label": arguments.label,
        "kind": "synthetic-transfer-only"
        if arguments.synthetic
        else "real-private-CR3-direct-conversion",
        "admission": "isolated allocation experiment; production API guard not exercised",
        "interval_seconds": 0.05,
        "starting_available_bytes": available,
        "safety_reserve_bytes": reserve,
        "worker_rss_cap_bytes": cap,
        "minimum_available_bytes": lowest_available,
        "sampled_peak_process_tree_rss_bytes": sampled_peak,
        "sampled_peak_output_disk_bytes": peak_disk,
        "peak_process_count_including_python_launcher": peak_workers,
        "conversion_worker_count": 1,
        "exit_code": process.returncode,
        "stopped": stopped,
        "worker": worker,
    }
    (arguments.output_dir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "worker"}, indent=2))
    if stopped or not worker or worker["status"] != "succeeded":
        raise SystemExit(1)
    print(
        json.dumps(
            {
                "status": worker["status"],
                "duration_seconds": worker["duration_seconds"],
                **worker["final_memory"],
            }
        )
    )


if __name__ == "__main__":
    main()
