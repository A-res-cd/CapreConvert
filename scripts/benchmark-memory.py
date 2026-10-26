"""External, file-backed LocalRAW memory benchmark. Never changes user workspaces or inputs.

Run the same harness against an immutable baseline EXE and the optimized EXE. RSS is
sampled for the application process tree; benchmark/client/browser memory is excluded.
Real workloads require private provenance-documented CR3 inputs. No decoder doubles.
"""

import argparse
import hashlib
import json
import os
import platform
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"completed", "completed_with_errors", "cancelled", "failed", "interrupted"}
SCENARIOS = ("idle", "single", "batch", "zip", "repeat", "cancel", "corrupt", "low-memory")
CHUNK = 1024**2


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def directory_bytes(root):
    size = 0
    for path in root.rglob("*"):
        try:
            if path.is_file():
                size += path.stat().st_size
        except FileNotFoundError:
            pass
    return size


def load_inputs(manifest=None, data_dir=None, provenance=None):
    """Keep originals read-only; require explicit provenance and stable file hashes."""
    if manifest:
        root = manifest.resolve().parent
        records = json.loads(manifest.read_text("utf-8-sig"))
    elif data_dir:
        if not provenance:
            raise ValueError("--data-dir requires --provenance describing permission/source.")
        root = data_dir.resolve()
        records = [
            {"filename": path.name, "provenance": provenance, "sha256": sha256(path)}
            for path in sorted(root.glob("*"))
            if path.is_file() and path.suffix.lower() == ".cr3"
        ]
    else:
        return []
    if not isinstance(records, list):
        raise ValueError("Fixture manifest must be a JSON list.")
    inputs = []
    for record in records:
        if not record.get("provenance") or not record.get("sha256"):
            raise ValueError("Each fixture requires provenance and sha256.")
        path = (root / record["filename"]).resolve()
        if not path.is_relative_to(root) or path.suffix.lower() != ".cr3" or not path.is_file():
            raise ValueError("Fixture path must be an existing CR3 inside its input directory.")
        if sha256(path) != record["sha256"]:
            raise ValueError(f"Fixture hash mismatch: {path.name}")
        inputs.append({**record, "path": path})
    return inputs


class MemorySampler:
    """Moderate sampling cadence; Windows also supplies process lifetime working-set peaks."""

    def __init__(self, pid, workspace, interval=0.2):
        self.pid, self.workspace, self.interval = pid, workspace, interval
        self.stop = threading.Event()
        self.thread = None
        self.samples = 0
        self.peak_tree_rss = self.peak_parent_rss = self.peak_children_rss = 0
        self.peak_process_count = self.peak_worker_count = 0
        self.peak_disk = 0
        self.peak_temporary_disk = 0
        self.minimum_available = psutil.virtual_memory().available
        self.process_lifetime_peaks = {}
        self.first = self.last = None

    def sample(self):
        try:
            parent = psutil.Process(self.pid)
            processes = [parent, *parent.children(recursive=True)]
        except psutil.NoSuchProcess:
            return
        parent_rss = children_rss = count = workers = 0
        for process in processes:
            try:
                memory = process.memory_info()
                count += 1
                if process.pid == self.pid:
                    parent_rss = memory.rss
                else:
                    children_rss += memory.rss
                    command = process.cmdline()
                    workers += any(
                        "--multiprocessing-fork" == part or "spawn_main" in part for part in command
                    )
                peak = getattr(memory, "peak_wset", None)
                if peak is not None:
                    key = str(process.pid)
                    self.process_lifetime_peaks[key] = max(self.process_lifetime_peaks.get(key, 0), peak)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        rss = parent_rss + children_rss
        point = {"tree_rss_bytes": rss, "parent_rss_bytes": parent_rss, "processes": count}
        if self.first is None:
            self.first = point
        self.last = point
        self.samples += 1
        self.peak_tree_rss = max(self.peak_tree_rss, rss)
        self.peak_parent_rss = max(self.peak_parent_rss, parent_rss)
        self.peak_children_rss = max(self.peak_children_rss, children_rss)
        self.peak_process_count = max(self.peak_process_count, count)
        self.peak_worker_count = max(self.peak_worker_count, workers)
        self.minimum_available = min(self.minimum_available, psutil.virtual_memory().available)
        self.peak_disk = max(self.peak_disk, directory_bytes(self.workspace))
        temporary = 0
        for path in self.workspace.rglob("*"):
            try:
                if path.is_file() and (
                    path.name.endswith(".part")
                    or any(part.startswith("document-") for part in path.parts)
                ):
                    temporary += path.stat().st_size
            except FileNotFoundError:
                continue
        self.peak_temporary_disk = max(self.peak_temporary_disk, temporary)

    def _loop(self):
        while not self.stop.wait(self.interval):
            self.sample()

    def __enter__(self):
        self.sample()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=5)
        self.sample()

    def result(self):
        return {
            "samples": self.samples,
            "sample_interval_seconds": self.interval,
            "peak_tree_rss_bytes": self.peak_tree_rss,
            "peak_parent_rss_bytes": self.peak_parent_rss,
            "peak_children_rss_bytes": self.peak_children_rss,
            "max_processes_including_server": self.peak_process_count,
            "max_conversion_workers": self.peak_worker_count,
            "windows_process_lifetime_peak_working_sets_bytes": self.process_lifetime_peaks,
            "minimum_system_available_bytes": self.minimum_available,
            "peak_workspace_bytes": self.peak_disk,
            "peak_temporary_bytes_sampled": self.peak_temporary_disk,
            "first": self.first,
            "last": self.last,
        }


class Application:
    def __init__(self, arguments, directory, config=None):
        self.arguments = arguments
        self.directory = directory
        self.workspace = directory / "workspace"
        self.config = config or {}
        self.process = self.client = None
        self.readers = []
        self.capabilities = {}

    def __enter__(self):
        self.directory.mkdir(parents=True)
        config = self.directory / "config.json"
        config.write_text(json.dumps(self.config), encoding="utf-8")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        command = (
            [str(self.arguments.executable)]
            if self.arguments.executable
            else [sys.executable, "-m", "localraw"]
        )
        command.extend(
            [
                "--no-browser",
                "--workspace",
                str(self.workspace),
                "--port",
                str(port),
                "--config",
                str(config),
            ]
        )
        environment = {
            key: value for key, value in os.environ.items() if not key.startswith("LOCALRAW_")
        }
        for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
            environment.pop(key, None)
        if self.arguments.executable and os.name == "nt":
            environment["PATH"] = str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32")
        error_path = getattr(self.arguments, "stderr_path", None)
        self.error_stream = error_path.open("w", encoding="utf-8") if error_path else None
        self.process = subprocess.Popen(
            command,
            cwd=self.directory if self.arguments.executable else self.arguments.source_root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=self.error_stream or subprocess.DEVNULL,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        credentials = queue.Queue()

        def read_console():
            for line in self.process.stdout:
                match = re.search(r"#bootstrap=([A-Za-z0-9_-]+)", line)
                if match:
                    credentials.put(match.group(1))

        self.readers = [threading.Thread(target=read_console, daemon=True)]
        self.readers[0].start()
        self.startup = MemorySampler(self.process.pid, self.workspace, self.arguments.interval)
        self.startup.__enter__()
        try:
            credential = credentials.get(timeout=45)
            self.client = httpx.Client(
                base_url=self.base, headers={"Origin": self.base}, timeout=30, trust_env=False
            )
            response = self.client.post("/api/v1/sessions", json={"credential": credential})
            response.raise_for_status()
            self.client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
            self.before_capabilities = self.process_memory()
            response = self.client.get("/api/v1/capabilities")
            response.raise_for_status()
            self.capabilities = response.json()
            self.after_capabilities = self.process_memory()
        except BaseException:
            self.startup.__exit__()
            self.__exit__()
            raise
        self.startup.__exit__()
        return self

    def __exit__(self, *args):
        if self.client:
            self.client.close()
        if self.process:
            try:
                parent = psutil.Process(self.process.pid)
                descendants = parent.children(recursive=True)
            except psutil.NoSuchProcess:
                descendants = []
            if self.process.poll() is None:
                self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            for descendant in descendants:
                try:
                    descendant.terminate()
                except psutil.NoSuchProcess:
                    pass
            psutil.wait_procs(descendants, timeout=5)
            for reader in self.readers:
                reader.join(timeout=2)
            self.process.stdout.close()
            if getattr(self, "error_stream", None):
                self.error_stream.close()

    def process_memory(self):
        process = psutil.Process(self.process.pid)
        return {
            "rss_bytes": process.memory_info().rss,
            "child_processes": len(process.children(recursive=True)),
        }

    def resources(self):
        """The baseline predates this optional, authenticated diagnostics endpoint."""
        response = self.client.get("/api/v1/resources")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def upload(self, path):
        registered = self.client.post(
            "/api/v1/uploads", json={"filename": path.name, "size_bytes": path.stat().st_size}
        )
        registered.raise_for_status()
        identifier = registered.json()["upload_id"]
        with path.open("rb") as stream:
            response = self.client.put(
                f"/api/v1/uploads/{identifier}/content",
                content=iter(lambda: stream.read(CHUNK), b""),
                headers={"Content-Length": str(path.stat().st_size)},
            )
        response.raise_for_status()
        return identifier

    def create_job(self, identifiers):
        response = self.client.post(
            "/api/v1/jobs",
            json={"upload_ids": identifiers, "settings": {"concurrency": 1, "jpeg_quality": 95}},
        )
        response.raise_for_status()
        return response.json()["id"]

    def wait(self, identifier, cancel_after=None):
        start = time.monotonic()
        deadline = start + self.arguments.timeout
        active_at = cancelled_at = None
        cancellation_response = None
        while time.monotonic() < deadline:
            response = self.client.get(f"/api/v1/jobs/{identifier}")
            response.raise_for_status()
            job = response.json()
            if job["state"] in TERMINAL:
                return job, {
                    "conversion_seconds": time.monotonic() - start,
                    "active_observed": active_at is not None,
                    "cancel_sent_during_work": cancelled_at is not None,
                    "cancellation_http_status": cancellation_response,
                    "cancellation_latency_seconds": time.monotonic() - cancelled_at
                    if cancelled_at
                    else None,
                }
            if job.get("active_files") and active_at is None:
                active_at = time.monotonic()
            if (
                cancel_after is not None
                and active_at is not None
                and cancelled_at is None
                and time.monotonic() - active_at >= cancel_after
            ):
                cancelled_at = time.monotonic()
                cancellation_response = self.client.post(f"/api/v1/jobs/{identifier}/cancel").status_code
            time.sleep(0.1)
        self.client.post(f"/api/v1/jobs/{identifier}/cancel")
        raise TimeoutError(f"Job did not finish within {self.arguments.timeout} seconds.")

    def files(self, identifier):
        items = []
        while True:
            response = self.client.get(
                f"/api/v1/jobs/{identifier}/files", params={"offset": len(items), "limit": 100}
            )
            response.raise_for_status()
            page = response.json()
            items.extend(page["items"])
            if len(items) >= page["total"]:
                return items


def inspect_jpeg(path, expected=None):
    from PIL import Image

    with Image.open(path) as image:
        image.load()
        if (
            image.format != "JPEG"
            or image.mode != "RGB"
            or image.getexif().get(274) != 1
            or not image.info.get("icc_profile")
        ):
            raise ValueError("JPEG format, RGB mode, orientation or ICC validation failed.")
        if expected and expected.get("width") and image.size != (expected["width"], expected["height"]):
            raise ValueError("JPEG dimensions differ from the fixture manifest.")
        sampling = image.layer
        if any(component[1:3] != (1, 1) for component in sampling):
            raise ValueError("Full-resolution JPEG chroma sampling differs from the 4:4:4 contract.")
        pixels = hashlib.sha256()
        for row in range(0, image.height, 128):
            with image.crop((0, row, image.width, min(image.height, row + 128))) as strip:
                pixels.update(strip.tobytes())
        return {
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "orientation": image.getexif()[274],
            "sampling": sampling,
            "sha256": sha256(path),
            "decoded_pixel_sha256": pixels.hexdigest(),
            "icc_sha256": hashlib.sha256(image.info["icc_profile"]).hexdigest(),
            "quantization_sha256": hashlib.sha256(
                json.dumps(image.quantization, sort_keys=True).encode()
            ).hexdigest(),
            "dimensions_match_manifest": bool(expected and expected.get("width")),
            "size_bytes": path.stat().st_size,
        }


def download_and_check(app, identifier, files, fixtures):
    output = []
    for index, item in enumerate(files):
        if item["state"] != "succeeded":
            continue
        path = app.directory / f"checked-{index}.jpg"
        try:
            with app.client.stream(
                "GET", f"/api/v1/jobs/{identifier}/results/{item['output_id']}"
            ) as response:
                response.raise_for_status()
                with path.open("wb") as stream:
                    for chunk in response.iter_bytes(CHUNK):
                        stream.write(chunk)
            source_name = Path(item["name"]).name
            expected = next((record for record in fixtures if record["path"].name == source_name), None)
            checked = inspect_jpeg(path, expected)
            if checked["sha256"] != item["sha256"]:
                raise ValueError("Downloaded JPEG hash differs from its committed result.")
            output.append({"source_name": source_name, **checked})
        finally:
            path.unlink(missing_ok=True)
    return output


def job_case(app, scenario, fixtures):
    paths = [record["path"] for record in fixtures]
    if scenario in {"single", "repeat", "corrupt", "low-memory"}:
        paths = paths[:1]
    if scenario in {"corrupt", "low-memory"}:
        corrupt = app.directory / "corrupt.cr3"
        corrupt.write_bytes(b"LocalRAW deliberate corrupt-input benchmark; not a RAW fixture.\n")
        paths = [corrupt]
    if scenario == "zip":
        archive = app.directory / "benchmark-inputs.zip"
        with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as zipped:
            for path in paths:
                zipped.write(path, "nested/" + path.name)
        paths = [archive]
    runs = app.arguments.repetitions if scenario == "repeat" else 1
    identifiers = []
    observations = []
    with MemorySampler(app.process.pid, app.workspace, app.arguments.interval) as sampler:
        upload_started = time.monotonic()
        identifiers = [app.upload(path) for path in paths]
        upload_seconds = time.monotonic() - upload_started
        for _ in range(runs):
            identifier = app.create_job(identifiers)
            job, timings = app.wait(
                identifier, app.arguments.cancel_after if scenario == "cancel" else None
            )
            files = app.files(identifier)
            observations.append({"job": job, "files": files, **timings})
            # Sample after worker exit; JPEG checking runs later in the driver process.
            time.sleep(0.3)
            observations[-1]["server_after_job"] = app.process_memory()
            observations[-1]["application_reported_resources"] = app.resources()
    outputs = []
    for observation in observations:
        checked = download_and_check(app, observation["job"]["id"], observation["files"], fixtures)
        observation["outputs"] = checked
        outputs.extend(checked)
    states = [observation["job"]["state"] for observation in observations]
    errors = [
        item["error"]
        for observation in observations
        for item in observation["files"]
        if item.get("error")
    ]
    if scenario == "cancel":
        status = "cancelled" if "cancelled" in states else "cancel_missed"
    elif scenario == "low-memory":
        status = (
            "policy_rejected"
            if errors and all("memory" in error.lower() for error in errors) and not outputs
            else "failed"
        )
    elif scenario == "corrupt":
        status = (
            "safe_failure" if all(state == "failed" for state in states) and not outputs else "failed"
        )
    elif all(state == "completed" for state in states) and outputs:
        status = "completed"
    elif errors and all("memory" in error.lower() for error in errors) and not outputs:
        status = "admission_rejected"
    else:
        status = "failed"
    leftovers = [path.name for path in app.workspace.rglob("*.part")]
    # Check explicit cancellation/extraction cleanup while keeping committed JPEGs valid.
    result = {
        "status": status,
        "upload_seconds": upload_seconds,
        "memory": sampler.result(),
        "job_states": states,
        "errors": errors,
        "runs": observations,
        "partial_files_remaining": leftovers,
        "temporary_extracted_raws_remaining": len(list((app.workspace / "jobs").rglob("*.cr3"))),
        "decoder_rejection_exercised": any(
            "corrupt or unsupported" in error.lower() for error in errors
        ),
        "full_resolution_outputs_verified": len(outputs),
    }
    for observation in observations:
        response = app.client.delete(f"/api/v1/jobs/{observation['job']['id']}")
        response.raise_for_status()
    for identifier in identifiers:
        response = app.client.delete(f"/api/v1/uploads/{identifier}")
        # Deleting the last referencing job also deletes its retained upload.
        if response.status_code != 404:
            response.raise_for_status()
    result["workspace_bytes_after_job_and_upload_deletion"] = directory_bytes(app.workspace)
    return result


@contextmanager
def measured_case(app):
    start = time.monotonic()
    result = {}
    try:
        yield result
    except Exception as exc:
        result.update(status="failed", exception=f"{type(exc).__name__}: {exc}")
    finally:
        result["duration_seconds"] = time.monotonic() - start


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--executable", type=Path, help="Immutable baseline or optimized EXE; otherwise launches source"
    )
    parser.add_argument("--source-root", type=Path, default=ROOT)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--manifest", type=Path)
    sources.add_argument("--data-dir", type=Path)
    parser.add_argument("--provenance")
    parser.add_argument(
        "--config",
        type=Path,
        help="Explicit app config; recorded in report, never modifies a saved config",
    )
    parser.add_argument("--label", default="memory")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--interval", type=float, default=0.2)
    parser.add_argument("--idle-seconds", type=float, default=3)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=3)
    parser.add_argument("--cancel-after", type=float, default=0.5)
    arguments = parser.parse_args(argv)
    if (
        not 0.1 <= arguments.interval <= 2
        or arguments.idle_seconds <= 0
        or arguments.timeout <= 0
        or arguments.repetitions < 1
        or arguments.batch_size < 1
        or arguments.cancel_after < 0
    ):
        parser.error(
            "Use interval 0.1-2s, positive durations/counts, and a nonnegative cancellation delay."
        )
    arguments.source_root = arguments.source_root.resolve()
    if arguments.executable:
        arguments.executable = arguments.executable.resolve()
        if not arguments.executable.is_file():
            parser.error("Executable not found.")
    arguments.output = (
        arguments.output or ROOT / "test-results" / f"memory-{arguments.label}.json"
    ).resolve()
    if arguments.output.exists():
        parser.error("Output report already exists; choose a new --output or label.")
    return arguments


def main(argv=None):
    arguments = parse_arguments(argv)
    fixtures = load_inputs(arguments.manifest, arguments.data_dir, arguments.provenance)
    fixtures = fixtures[: arguments.batch_size]
    config = json.loads(arguments.config.read_text("utf-8-sig")) if arguments.config else {}
    for key in ("workspace", "port", "tls_cert", "tls_key", "lan", "allowed_hosts"):
        if key in config:
            raise ValueError(f"Benchmark controls {key}; remove it from --config.")
    report = {
        "schema_version": 1,
        "label": arguments.label,
        "recorded_at": datetime.now(UTC).isoformat(),
        "target": str(arguments.executable or arguments.source_root),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "system_total_bytes": psutil.virtual_memory().total,
        "explicit_config_overrides": config,
        "measurement_notes": [
            "RSS sums server and descendants; shared DLL pages can be counted more than once.",
            "Sampled RSS peaks are lower bounds at the chosen interval; Windows process lifetime peaks are recorded separately and are not summed.",
            "Benchmark driver and browser memory are excluded; no browser is launched.",
            "Low-memory scenario increases the configured reserve; it does not exhaust host RAM.",
            "CR3 originals remain read-only. No mock decoder is used. JPEG checking runs after worker exit in the driver.",
        ],
        "inputs": [
            {key: value for key, value in record.items() if key != "path"} for record in fixtures
        ],
        "scenarios": {},
    }
    artifacts = ROOT / "test-results"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="memory-benchmark-", dir=artifacts) as temporary:
        temporary = Path(temporary).resolve()
        if temporary.parent != artifacts.resolve():
            raise RuntimeError("Unverified benchmark temporary directory.")
        normal = [name for name in arguments.scenarios if name != "low-memory"]
        if normal:
            with Application(arguments, temporary / "normal", config) as app:
                report["capabilities"] = app.capabilities
                report["startup"] = app.startup.result()
                report["idle_before_capabilities"] = app.before_capabilities
                report["idle_after_capabilities"] = app.after_capabilities
                for scenario in normal:
                    with measured_case(app) as result:
                        if scenario == "idle":
                            with MemorySampler(
                                app.process.pid, app.workspace, arguments.interval
                            ) as sampler:
                                time.sleep(arguments.idle_seconds)
                            result.update(status="completed", memory=sampler.result())
                        elif scenario != "corrupt" and not fixtures:
                            result.update(
                                status="blocked", reason="No provenance-documented CR3 inputs supplied."
                            )
                        else:
                            result.update(job_case(app, scenario, fixtures))
                    report["scenarios"][scenario] = result
                    print(json.dumps({"scenario": scenario, "status": result["status"]}), flush=True)
        if "low-memory" in arguments.scenarios:
            constrained = {**config, "memory_reserve_bytes": psutil.virtual_memory().total + 1024**3}
            # Newer source may defer admission; bound this deterministic policy test without host stress.
            if "memory_wait_seconds" in report.get("capabilities", {}).get("limits", {}):
                constrained["memory_wait_seconds"] = 1
            with Application(arguments, temporary / "constrained", constrained) as app:
                with measured_case(app) as result:
                    result.update(job_case(app, "low-memory", fixtures))
                    result["policy_simulation"] = True
                    result["configured_reserve_bytes"] = constrained["memory_reserve_bytes"]
                report["scenarios"]["low-memory"] = result
                print(json.dumps({"scenario": "low-memory", "status": result["status"]}), flush=True)
    report["original_hashes_unchanged"] = all(
        sha256(record["path"]) == record["sha256"] for record in fixtures
    )
    if not report["original_hashes_unchanged"]:
        raise RuntimeError("An input hash changed during the benchmark.")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"report": str(arguments.output), "original_hashes_unchanged": True}), flush=True)


if __name__ == "__main__":
    main()
