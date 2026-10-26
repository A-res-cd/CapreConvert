"""One bounded supervisor. Jobs are persisted; each image gets its own spawn process."""

import copy
import hashlib
import json
import multiprocessing
import os
import shutil
import threading
import time
from collections import deque
from pathlib import PurePosixPath

import psutil

from .archives import OutputNames, extract_selected, inspect_archive, package_outputs, safe_relative
from .config import PREVIEW_MAX_BYTES, THUMBNAIL_MAX_BYTES, MiB
from .errors import Problem
from .formats import format_for, output_budget
from .memory import (
    HEADER_MEMORY_BYTES,
    MIN_RESERVE_BYTES,
    admission_error,
    available_budget,
    gibibytes,
    process_memory,
    render_budget,
)
from .models import (
    FILE_TERMINAL,
    FILE_TRANSITIONS,
    JOB_TERMINAL,
    JOB_TRANSITIONS,
    ConversionSettings,
    transition,
)
from .storage import atomic_json, file_hash, opaque_id, valid_id
from .worker import run_worker


def memory_estimate(pixels):
    return render_budget(pixels)


def worker_rss(pid):
    return process_memory(pid).rss


def public_file(item):
    return {
        key: copy.deepcopy(value) for key, value in item.items() if key not in {"upload_id", "entry"}
    }


def counters(job):
    result = {"total": 0, "succeeded": 0, "failed": 0, "skipped": 0, "cancelled": 0, "finished": 0}
    for item in job["files"]:
        count = item.get("skipped_count", 1)
        result["total"] += count
        if item["state"] in FILE_TERMINAL:
            result["finished"] += count
            result[item["state"]] += count
    return result


def public_job(job):
    fields = ("id", "state", "settings", "created_at", "expires_at", "package_status", "warnings")
    result = {field: copy.deepcopy(job[field]) for field in fields}
    result["settings"].setdefault("conversion", "cr3_to_jpg")
    result["counters"] = counters(job)
    result["active_files"] = [
        public_file(item)
        for item in job["files"]
        if item["state"] not in FILE_TERMINAL and item["state"] != "queued"
    ]
    return result


class Jobs:
    def __init__(self, workspace, settings, uploads, worker_target=run_worker):
        self.workspace, self.settings, self.uploads = workspace, settings, uploads
        self.worker_target = worker_target
        self.items = {}
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.context = multiprocessing.get_context("spawn")
        self.thread = None
        self.export_lock = threading.Lock()
        self.execution_lock = threading.Lock()
        self.preview_slots = threading.BoundedSemaphore(settings.preview_pending_requests)
        self._memory_snapshot = {}
        self._memory_sampled_at = 0.0
        self._application_peak = 0
        self._conversion_workers = 0
        self._pressure_since = None
        for path in (workspace.root / "manifests").glob("job-*.json"):
            try:
                job = json.loads(path.read_text("utf-8"))
                if (
                    job["id"] != path.stem.removeprefix("job-")
                    or not valid_id(job["id"])
                    or not valid_id(job["owner"])
                    or any(not valid_id(identifier) for identifier in job["upload_ids"])
                    or job["state"] not in JOB_TERMINAL | JOB_TRANSITIONS.keys()
                ):
                    continue
                ConversionSettings.model_validate(job["settings"])
                if any(
                    not valid_id(item["id"])
                    or not valid_id(item["output_id"])
                    or item["state"] not in FILE_TERMINAL | FILE_TRANSITIONS.keys()
                    for item in job["files"]
                ):
                    continue
                for item in job["files"]:
                    if "output_name" in item:
                        safe_relative(item["output_name"])
                    if item.get("preview") and (
                        not isinstance(item["preview"], dict)
                        or not isinstance(item["preview"].get("thumbnail"), dict)
                    ):
                        item["preview"] = None
                        item["warnings"].append(
                            "Retained preview metadata is invalid; the converted result remains available."
                        )
                if job["state"] not in JOB_TERMINAL:
                    transition(job, "interrupted")
                    job["expires_at"] = time.time() + settings.retention_seconds
                    job["warnings"].append(
                        "Host restarted; unfinished work interrupted. Retry explicitly."
                    )
                    for item in job["files"]:
                        if item["state"] not in FILE_TERMINAL:
                            item["state"] = "cancelled"
                for item in job["files"]:
                    if item["state"] == "succeeded":
                        output = self.output_path(job, item)
                        if (
                            not output.is_file()
                            or output.stat().st_size != item.get("size_bytes")
                            or (item.get("sha256") and file_hash(output) != item["sha256"])
                        ):
                            item["state"], item["error"] = (
                                "failed",
                                "Retained result is missing or damaged.",
                            )
                            job["package_status"] = "failed"
                            if job["state"] == "completed":
                                job["state"] = "completed_with_errors"
                        if item.get("preview"):
                            for kind in ("preview", "thumbnail"):
                                metadata = (
                                    item["preview"]
                                    if kind == "preview"
                                    else item["preview"].get("thumbnail", {})
                                )
                                derivative = self.preview_path(job, item, thumbnail=kind == "thumbnail")
                                if (
                                    not derivative.is_file()
                                    or derivative.stat().st_size != metadata.get("size_bytes")
                                    or file_hash(derivative) != metadata.get("sha256")
                                ):
                                    item["preview"] = None
                                    item["warnings"].append(
                                        "Retained preview missing or damaged; the converted result remains available."
                                    )
                                    break
                # Staging and uncommitted outputs are never recovered as successful results.
                committed = {
                    self.output_path(job, item).name
                    for item in job["files"]
                    if item["state"] == "succeeded"
                }
                for item in job["files"]:
                    if item["state"] == "succeeded" and item.get("preview"):
                        committed.update(
                            self.preview_path(job, item, thumbnail=thumbnail).name
                            for thumbnail in (False, True)
                        )
                job["exports"] = [
                    item
                    for item in job.get("exports", [])
                    if isinstance(item, dict)
                    and valid_id(item.get("id"))
                    and isinstance(item.get("fingerprint"), str)
                    and len(item["fingerprint"]) == 64
                    and isinstance(item.get("count"), int)
                    and item["count"] > 0
                    and self.export_path(job, item).is_file()
                    and self.export_path(job, item).stat().st_size == item.get("size_bytes")
                ]
                committed.update(self.export_path(job, item).name for item in job["exports"])
                # Cache metadata is JSON only; document parsing stays in workers.
                from .previews import cache_identity

                completed = {
                    item["output_id"]: item for item in job["files"] if item["state"] == "succeeded"
                }
                for sidecar in self.directory(job).glob("pv-*.meta"):
                    try:
                        if sidecar.stat().st_size > settings.preview_max_bytes:
                            continue
                        cache = json.loads(sidecar.read_text("utf-8"))
                        if not isinstance(cache, dict) or not isinstance(cache.get("details"), dict):
                            continue
                        item = completed.get(cache.get("output_id"))
                        details = cache["details"]
                        descriptor = format_for(job["settings"])
                        identity = (
                            cache_identity(
                                item, descriptor.preview_kind, details.get("page", 1), settings
                            )
                            if item
                            else None
                        )
                        target = sidecar.with_suffix("")
                        if (
                            identity
                            and cache.get("fingerprint") == identity
                            and target.name
                            == "pv-"
                            + identity
                            + (".json" if descriptor.preview_kind == "docx" else ".png")
                            and target.is_file()
                            and target.stat().st_size <= settings.preview_max_bytes
                            and file_hash(target) == cache["sha256"]
                        ):
                            committed.update((target.name, sidecar.name))
                    except (OSError, ValueError, TypeError, KeyError):
                        pass

                for retained in self.directory(job).glob("*"):
                    if (
                        retained.is_file()
                        and retained.name != "results.zip"
                        and retained.name not in committed
                    ):
                        retained.unlink(missing_ok=True)
                for item in job["files"]:
                    self._clear_document_scratch(job, item)
                if job["package_status"] == "ready" and not self.archive_path(job).is_file():
                    job["package_status"] = "failed"
                self.items[job["id"]] = job
                for identifier in job["upload_ids"]:
                    if identifier in uploads.items:
                        uploads.items[identifier]["refs"].append(job["id"])
                self.save(job)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        for upload in uploads.items.values():
            uploads.save(upload)

    def start(self):
        self.thread = threading.Thread(target=self._loop, name="localraw-supervisor", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=self.settings.cancel_grace_seconds + 15)
            if self.thread.is_alive():
                raise RuntimeError("Supervisor still stopping; workspace ownership must be retained.")

    def directory(self, job):
        return self.workspace.root / "jobs" / job["id"]

    def output_path(self, job, item):
        return self.directory(job) / (item["output_id"] + format_for(job["settings"]).output_extension)

    def archive_path(self, job):
        return self.directory(job) / "results.zip"

    def preview_path(self, job, item, thumbnail=False):
        kind = "thumbnail" if thumbnail else "preview"
        metadata = item.get("preview") or {}
        if thumbnail:
            metadata = metadata.get("thumbnail", {})
        extension = ".png" if metadata.get("extension") == ".png" else ".jpg"
        return self.directory(job) / (item["output_id"] + f".{kind}{extension}")

    def export_path(self, job, export):
        return self.directory(job) / ("selection-" + export["id"] + ".zip")

    def document_scratch(self, job, item):
        return self.directory(job) / ("document-" + item["output_id"])

    def _clear_document_scratch(self, job, item):
        target = self.document_scratch(job, item)
        if target.exists():
            checked = target.resolve()
            if checked.parent != self.directory(job).resolve() or not valid_id(item["output_id"]):
                raise RuntimeError("Invalid generated document scratch directory.")
            shutil.rmtree(checked)

    def prepare_export(self, owner, job_id, output_ids):
        """Bounded packaging in an HTTP worker thread, outside the event loop."""
        with self.workspace.lock:
            job = self.owned(job_id, owner)
            wanted = set(output_ids)
            selected = [
                item
                for item in job["files"]
                if item["state"] == "succeeded" and item["output_id"] in wanted
            ]
            if len(selected) != len(wanted) or any(
                not self.output_path(job, item).is_file() for item in selected
            ):
                raise Problem(404, "RESULT_NOT_FOUND", "One or more selected results are unavailable.")
            fingerprint = hashlib.sha256(json.dumps(sorted(wanted)).encode()).hexdigest()
            exports = job.setdefault("exports", [])
            cached = next(
                (
                    item
                    for item in exports
                    if item["fingerprint"] == fingerprint and self.export_path(job, item).is_file()
                ),
                None,
            )
            if cached:
                return {
                    "export_id": cached["id"],
                    "count": cached["count"],
                    "size_bytes": cached["size_bytes"],
                }
            if len(exports) >= self.settings.export_cache_per_job:
                if self.workspace.downloads.get(job_id, 0):
                    raise Problem(
                        409,
                        "EXPORT_CACHE_BUSY",
                        "Wait for current downloads to finish, then export again.",
                    )
                while len(exports) >= self.settings.export_cache_per_job:
                    self.export_path(job, exports.pop(0)).unlink(missing_ok=True)
                self.save(job)
            if not self.export_lock.acquire(blocking=False):
                raise Problem(
                    409, "EXPORT_BUSY", "Another selection is being prepared. Try again shortly."
                )
            lease = self.workspace.downloading(job_id)
            lease.__enter__()
            export = {
                "id": opaque_id(),
                "fingerprint": fingerprint,
                "count": len(selected),
                "created_at": time.time(),
            }
            destination = self.export_path(job, export)
        key = "export-" + export["id"]
        committed = False
        try:
            total = (
                sum(
                    self.output_path(job, item).stat().st_size
                    + 2 * len(item["output_name"].encode())
                    + 256
                    for item in selected
                )
                + MiB
            )
            self.workspace.reserve(key, total)
            package_outputs(
                destination,
                [
                    {"path": self.output_path(job, item), "output_name": item["output_name"]}
                    for item in selected
                ],
                lambda n: self.workspace.consume(key, n),
                self.stop.is_set,
            )
            with self.workspace.lock:
                export["size_bytes"] = destination.stat().st_size
                exports.append(export)
                try:
                    self.save(job)
                except OSError:
                    exports.remove(export)
                    raise
                committed = True
            return {
                "export_id": export["id"],
                "count": export["count"],
                "size_bytes": export["size_bytes"],
            }
        except (OSError, ValueError) as exc:
            raise Problem(
                507,
                "EXPORT_FAILED",
                "Selected results could not be packaged. Individual downloads remain available.",
            ) from exc
        finally:
            if not committed:
                destination.unlink(missing_ok=True)
            self.workspace.release(key)
            lease.__exit__(None, None, None)
            self.export_lock.release()

    def save(self, job):
        with self.workspace.lock:
            atomic_json(self.workspace.manifest("job", job["id"]), job)

    def owned(self, job_id, owner):
        job = self.items.get(job_id)
        if not job or job["owner"] != owner:
            raise Problem(404, "JOB_NOT_FOUND", "Job not found.")
        return job

    def create(self, owner, request, key=None):
        if key and len(key) > 128:
            raise Problem(422, "INVALID_IDEMPOTENCY_KEY", "Idempotency key exceeds 128 characters.")
        digest = hashlib.sha256(json.dumps(request.model_dump(), sort_keys=True).encode()).hexdigest()
        with self.workspace.lock:
            if key:
                for job in self.items.values():
                    if job["owner"] == owner and job.get("idempotency_key") == key:
                        if job["payload_hash"] != digest and not (
                            job["upload_ids"] == request.upload_ids
                            and ConversionSettings.model_validate(job["settings"]) == request.settings
                        ):
                            raise Problem(
                                409,
                                "IDEMPOTENCY_CONFLICT",
                                "Key already used with different job inputs.",
                            )
                        return public_job(job)
            pending = [job for job in self.items.values() if job["state"] not in JOB_TERMINAL]
            if (
                len(pending) >= self.settings.global_pending_jobs
                or sum(job["owner"] == owner for job in pending) >= self.settings.session_pending_jobs
            ):
                raise Problem(429, "QUEUE_FULL", "Job queue is full. Wait for current work to finish.")
            if request.settings.concurrency > self.settings.max_concurrency:
                raise Problem(422, "INVALID_CONCURRENCY", "Concurrency exceeds this host's limit.")
            inputs = [self.uploads.owned(identifier, owner) for identifier in request.upload_ids]
            if any(item["state"] != "ready" for item in inputs):
                raise Problem(409, "UPLOAD_NOT_READY", "Every input must finish uploading first.")
            descriptor = format_for(request.settings)
            if any(
                PurePosixPath(item["filename"]).suffix.lower() not in descriptor.input_extensions
                for item in inputs
            ):
                raise Problem(
                    422, "INPUT_FORMAT_MISMATCH", "These inputs do not match the selected conversion."
                )
            if sum(item["size_bytes"] for item in inputs) > self.settings.job_upload_max_bytes:
                raise Problem(413, "JOB_TOO_LARGE", "Total uploaded job bytes exceed the limit.")
            self.workspace.check_capacity()
            identifier = opaque_id()
            job = {
                "id": identifier,
                "owner": owner,
                "state": "queued",
                "files": [],
                "settings": request.settings.model_dump(),
                "upload_ids": list(request.upload_ids),
                "created_at": time.time(),
                "expires_at": None,
                "warnings": [],
                "package_status": "pending",
                "idempotency_key": key,
                "payload_hash": digest,
            }
            self.directory(job).mkdir(mode=0o700)
            self.save(job)
            self.items[identifier] = job
            for upload in inputs:
                upload["refs"].append(identifier)
                self.uploads.save(upload)
            self.wake.set()
            return public_job(job)

    def cancel(self, owner, identifier):
        with self.workspace.lock:
            job = self.owned(identifier, owner)
            if job["state"] not in JOB_TERMINAL:
                queued = job["state"] == "queued"
                transition(job, "cancelling")
                if queued:
                    transition(job, "cancelled")
                    job["expires_at"] = time.time() + self.settings.retention_seconds
                    job["package_status"] = "unavailable"
                self.save(job)
                self.wake.set()
            return public_job(job)

    def delete(self, owner, identifier):
        with self.workspace.lock:
            job = self.owned(identifier, owner)
            if job["state"] not in JOB_TERMINAL or self.workspace.downloads.get(identifier, 0):
                raise Problem(409, "JOB_BUSY", "Job is active or a download is in progress.")
            target = self.directory(job).resolve()
            if target.parent != (self.workspace.root / "jobs").resolve():
                raise RuntimeError("Invalid managed job directory")
            if target.exists():
                shutil.rmtree(target)
            self.workspace.manifest("job", identifier).unlink(missing_ok=True)
            del self.items[identifier]
            for upload_id in job["upload_ids"]:
                upload = self.uploads.items.get(upload_id)
                if upload:
                    upload["refs"] = [ref for ref in upload["refs"] if ref != identifier]
                    if not upload["refs"]:
                        self.uploads.delete(owner, upload_id)
                    else:
                        self.uploads.save(upload)

    def cleanup(self):
        with self.workspace.lock:
            for job in list(self.items.values()):
                if (
                    job["state"] in JOB_TERMINAL
                    and job["expires_at"] is not None
                    and job["expires_at"] < time.time()
                    and not self.workspace.downloads.get(job["id"])
                ):
                    self.delete(job["owner"], job["id"])
            self.uploads.cleanup()

    def _loop(self):
        cleanup_at = 0
        while not self.stop.is_set():
            try:
                if time.monotonic() >= cleanup_at:
                    self.cleanup()
                    cleanup_at = time.monotonic() + self.settings.cleanup_seconds
                with self.workspace.lock:
                    job = next(
                        (job for job in self.items.values() if job["state"] in {"queued", "cancelling"}),
                        None,
                    )
                if job:
                    with self.execution_lock:
                        self._run_job(job)
                else:
                    self.wake.wait(0.25)
                    self.wake.clear()
            except Exception:
                # One bad input or workspace I/O error never kills the scheduler.
                if "job" in locals() and job and job["state"] not in JOB_TERMINAL:
                    with self.workspace.lock:
                        for item in job["files"]:
                            if item["state"] not in FILE_TERMINAL:
                                transition(item, "failed", file=True)
                                item["error"] = "Host could not finish this file."
                        transition(job, "cancelled" if job["state"] == "cancelling" else "failed")
                        job["expires_at"] = time.time() + self.settings.retention_seconds
                        job["warnings"].append(
                            "Host could not finish this job; committed results remain available."
                        )
                        try:
                            self.save(job)
                        except OSError:
                            pass
                self.stop.wait(0.25)

    def _new_file(self, upload, name, state="queued", **extras):
        return {
            "id": opaque_id(),
            "output_id": opaque_id(),
            "upload_id": upload["id"],
            "name": name,
            "state": state,
            "warnings": [],
            "error": None,
            **extras,
        }

    def _inspect(self, job):
        names, total_raw, expanded = OutputNames(), 0, 0
        descriptor = format_for(job["settings"])
        for upload_id in job["upload_ids"]:
            if self._cancelled(job):
                break
            upload = self.uploads.items[upload_id]
            try:
                if PurePosixPath(upload["filename"]).suffix.lower() == ".zip":
                    if not descriptor.archive_input:
                        raise ValueError("ZIP input is supported only for RAW conversions.")
                    entries, skipped, declared = inspect_archive(
                        self.uploads.path(upload), self.settings
                    )
                    if expanded + declared > self.settings.expanded_max_bytes:
                        raise ValueError("Archives exceed the total job expanded-byte limit.")
                    if total_raw + len(entries) > self.settings.max_files:
                        raise ValueError("Archive exceeds the remaining RAW file count limit.")
                    root = names.archive_root(upload["filename"])
                    tasks = [
                        self._new_file(
                            upload,
                            f"{upload['filename']}/{entry['relative']}",
                            entry=entry,
                            output_name=names.output(
                                f"{root}/{entry['relative']}",
                                job["settings"]["filename_suffix"],
                                descriptor.output_extension,
                            ),
                        )
                        for entry in entries
                    ]
                    if skipped:
                        tasks.append(
                            self._new_file(
                                upload,
                                upload["filename"],
                                "skipped",
                                skipped_count=len(skipped),
                                skipped_names=skipped[:100],
                                warnings=[
                                    f"Skipped {len(skipped)} unsupported entries; nested ZIPs are not opened."
                                ],
                            )
                        )
                    if not entries:
                        job["warnings"].append(f"No CR3 files found in {upload['filename']}.")
                    expanded += declared
                    total_raw += len(entries)
                else:
                    if total_raw >= self.settings.max_files:
                        raise ValueError("Job exceeds the file count limit.")
                    tasks = [
                        self._new_file(
                            upload,
                            upload["filename"],
                            output_name=names.output(
                                "files/" + upload["filename"],
                                job["settings"]["filename_suffix"],
                                descriptor.output_extension,
                            ),
                        )
                    ]
                    total_raw += 1
                with self.workspace.lock:
                    for task in tasks:
                        task["output_extension"] = descriptor.output_extension
                        task["media_type"] = descriptor.media_type
                    job["files"].extend(tasks)
            except ValueError as exc:
                with self.workspace.lock:
                    job["files"].append(
                        self._new_file(upload, upload["filename"], "failed", error=str(exc))
                    )
            self.save(job)

    def _cancelled(self, job):
        return self.stop.is_set() or job["state"] == "cancelling"

    def _read_workers(self, active):
        workers = {}
        for identifier, task in active.items():
            try:
                pid = getattr(task["process"], "pid", None)
                resident = worker_rss(pid) if pid else 0
            except psutil.NoSuchProcess:
                resident = 0
            except psutil.Error:
                resident = 0
                task["error"] = (
                    "Host could not monitor conversion-worker memory safely. Retry this file."
                )
            task["rss"] = resident
            task["peak_rss"] = max(task.get("peak_rss", 0), resident)
            workers[identifier] = {"budget": task["budget"], "rss": resident}
        return workers

    def _available_memory(self, active, excluding=None, *, workers=None, available=None):
        workers = self._read_workers(active) if workers is None else workers
        available = psutil.virtual_memory().available if available is None else available
        return available_budget(available, self.settings.memory_reserve_bytes, workers, excluding)

    def memory_status(self):
        """Authenticated, path-free host diagnostics. Peaks are sampled working sets."""
        with self.workspace.lock:
            now = time.monotonic()
            if now - self._memory_sampled_at >= self.settings.memory_poll_seconds:
                try:
                    memory = process_memory(os.getpid())
                    self._application_peak = max(self._application_peak, memory.rss)
                    self._memory_snapshot = {
                        "system_available_bytes": psutil.virtual_memory().available,
                        "safety_reserve_bytes": self.settings.memory_reserve_bytes,
                        "application_rss_bytes": memory.rss,
                        "application_peak_sampled_rss_bytes": self._application_peak,
                        "process_count": memory.processes,
                        "sample_interval_seconds": self.settings.memory_poll_seconds,
                        "metric": "sum of process-tree RSS; shared pages may be counted more than once",
                        "diagnostics_available": True,
                    }
                except psutil.Error:
                    # Optional aggregate diagnostics must not abort sibling conversions.
                    # Worker-specific monitoring failures still stop that worker safely.
                    self._memory_snapshot["diagnostics_available"] = False
                self._memory_sampled_at = now
            self._memory_snapshot["conversion_workers"] = self._conversion_workers
            return copy.deepcopy(self._memory_snapshot)

    def _send_admission(self, task, admitted):
        try:
            task["connection"].send({"admitted": admitted})
        except (OSError, EOFError, ValueError):
            task["error"] = (
                task["error"] or "Image worker exited while waiting for memory. Retry this file."
            )

    def _admit_render(self, job, task, active, workers=None, available=None):
        required = task.get("requested_budget")
        if required is None or task.get("admitted") or task["error"]:
            return
        workers = self._read_workers(active) if workers is None else workers
        available = psutil.virtual_memory().available if available is None else available
        if task.get("rss", 0) > task["budget"]:
            task["error"] = "Image worker exceeded its memory budget during header inspection."
        if self._cancelled(job):
            task["error"] = "Conversion cancelled while waiting for memory."
        if task["error"]:
            self._send_admission(task, False)
            return
        room = self._available_memory(active, task["item"]["id"], workers=workers, available=available)
        cap = self.settings.worker_memory_bytes
        if cap is not None and required > cap:
            task["error"] = (
                f"The conversion budget ({gibibytes(required)}) exceeds the configured "
                f"worker limit ({gibibytes(cap)}). Use a host/limit with sufficient memory."
            )
        elif required <= room:
            task["budget"] = required
            task["admitted"] = True
            task["item"].setdefault("memory", {}).update(
                {"budget_bytes": required, "waiting": False, "admission_available_bytes": available}
            )
            self._send_admission(task, True)
            return
        elif any(other is not task for other in active.values()):
            # Another admitted worker can finish and release its growth reservation.
            # Leave this one parked before unpacking; total timeout/cancel still apply.
            task["item"].setdefault("memory", {})["waiting"] = True
            warning = "Available memory limits parallel processing; some images may wait."
            if warning not in job["warnings"]:
                job["warnings"].append(warning)
            return
        else:
            needed = required - min(task.get("rss", 0), task["budget"])
            engine = format_for(job.get("settings", {})).engine
            kind = (
                "full-resolution image"
                if engine == "raw"
                else "image"
                if engine == "raster"
                else "document"
            )
            task["error"] = f"Not enough available memory for the {kind}. " + admission_error(
                available, needed + self.settings.memory_reserve_bytes
            )
        self._send_admission(task, False)

    def _start_file(self, job, item, active):
        identifier = item["id"]
        budget = HEADER_MEMORY_BYTES
        if active:
            # Inspect one unknown image at a time. A second worker is optional and
            # starts only with room for a render comparable to the active image.
            if any(not task.get("admitted") for task in active.values()):
                return False
            anticipated = max(task["budget"] for task in active.values())
            if self._available_memory(active) < anticipated:
                return False
        if self._available_memory(active) < budget:
            if active:
                return False
            raise ValueError(
                admission_error(
                    psutil.virtual_memory().available, budget + self.settings.memory_reserve_bytes
                )
            )
        descriptor = format_for(job["settings"])
        reserve = (
            output_budget(self.settings.max_pixels, descriptor.output_extension)
            + PREVIEW_MAX_BYTES
            + THUMBNAIL_MAX_BYTES
            if descriptor.engine == "raw"
            else self.settings.raster_output_max_bytes + PREVIEW_MAX_BYTES + THUMBNAIL_MAX_BYTES
            if descriptor.engine == "raster"
            else 2 * self.settings.document_output_max_bytes
            + self.settings.document_expanded_max_bytes
            + self.settings.document_max_bytes
        )
        if "entry" in item:
            reserve += item["entry"]["size_bytes"]
        self.workspace.reserve(identifier, reserve)
        upload = self.uploads.items[item["upload_id"]]
        source = self.uploads.path(upload)
        staged = None
        try:
            if "entry" in item:
                with self.workspace.lock:
                    transition(item, "extracting", file=True)
                self.save(job)
                staged = self.directory(job) / (identifier + ".cr3")
                extract_selected(
                    source,
                    item["entry"],
                    staged,
                    self.settings,
                    lambda n: self.workspace.consume(identifier, n),
                    lambda: self._cancelled(job),
                )
                source = staged
            if self._cancelled(job):
                raise ValueError("Conversion cancelled.")
            with self.workspace.lock:
                transition(item, "decoding", file=True)
            parent, child = self.context.Pipe()
            stop = self.context.Event()
            process = self.context.Process(
                target=self.worker_target,
                args=(
                    str(source),
                    str(self.output_path(job, item)),
                    job["settings"],
                    {
                        "max_pixels": self.settings.max_pixels,
                        "min_free_bytes": self.settings.min_free_bytes,
                        "exiftool": str(self.settings.exiftool) if self.settings.exiftool else None,
                        "libreoffice": str(self.settings.libreoffice)
                        if self.settings.libreoffice
                        else None,
                        "scratch_dir": str(self.document_scratch(job, item)),
                        **{
                            field: getattr(self.settings, field)
                            for field in (
                                "raster_max_bytes",
                                "raster_output_max_bytes",
                                "raster_max_dimension",
                                "raster_header_max_bytes",
                                "document_max_bytes",
                                "document_output_max_bytes",
                                "document_expanded_max_bytes",
                                "document_max_pages",
                                "document_max_characters",
                                "pdf_page_content_max_bytes",
                                "document_memory_bytes",
                                "file_timeout_seconds",
                            )
                        },
                    },
                    child,
                    stop,
                ),
                name="capreconvert-file",
            )
            try:
                process.start()
            except BaseException:
                parent.close()
                process.close()
                raise
            finally:
                child.close()
            active[identifier] = {
                "item": item,
                "process": process,
                "connection": parent,
                "stop": stop,
                "started": time.monotonic(),
                "cancel_at": None,
                "budget": budget,
                "admitted": False,
                "peak_rss": 0,
                "staged": staged,
                "result": None,
                "error": None,
            }
            self.save(job)
            return True
        except BaseException:
            if staged:
                staged.unlink(missing_ok=True)
            self.workspace.release(identifier)
            raise

    def _message(self, job, task, active, message):
        item = task["item"]
        if "pixels" in message:
            estimate = memory_estimate(message["pixels"])
            task["requested_budget"] = estimate
            self._admit_render(job, task, active)
        elif "raster_pixels" in message:
            pixels = message["raster_pixels"]
            if not isinstance(pixels, int) or not 0 < pixels <= self.settings.max_pixels:
                task["error"] = "Invalid raster dimension admission."
                self._send_admission(task, False)
            else:
                task["requested_budget"] = max(HEADER_MEMORY_BYTES, 128 * MiB + pixels * 40)
                self._admit_render(job, task, active)
        elif "memory_request" in message:
            # This is a host-chosen document cap, never a client-provided budget.
            task["requested_budget"] = self.settings.document_memory_bytes
            self._admit_render(job, task, active)
        elif "memory" in message:
            measured = message["memory"]
            task["peak_rss"] = max(task.get("peak_rss", 0), measured["peak_rss_bytes"])
            item.setdefault("memory", {}).update(measured)
        elif "stage" in message:
            with self.workspace.lock:
                transition(item, message["stage"], file=True)
            self.save(job)
        elif "result" in message:
            task["result"] = message["result"]
        elif "error" in message:
            task["error"] = task["error"] or message["error"]

    def _collect_messages(self, job, task, active):
        try:
            while task["connection"].poll():
                self._message(job, task, active, task["connection"].recv())
        except (EOFError, BrokenPipeError, OSError):
            pass

    def _check_memory(self, job, active):
        available = psutil.virtual_memory().available
        workers = self._read_workers(active)
        for identifier, task in active.items():
            self._admit_render(job, task, active, workers, available)
            workers[identifier]["budget"] = task["budget"]
            if task.get("rss", 0) > task["budget"]:
                task["error"] = "Image worker exceeded its memory budget. Retry after freeing memory."
        now = time.monotonic()
        if active and available < self.settings.memory_reserve_bytes:
            if self._pressure_since is None:
                self._pressure_since = now
            if available < MIN_RESERVE_BYTES or now - self._pressure_since >= 1.0:
                # Release one worker first, preserving other committed successes.
                victim = next((task for task in reversed(active.values()) if not task["error"]), None)
                if victim:
                    victim["error"] = (
                        f"Available system memory fell to {gibibytes(available)} during conversion. "
                        "The worker was stopped safely; close memory-heavy apps and retry."
                    )
                self._pressure_since = None
        else:
            self._pressure_since = None
        self._conversion_workers = len(active)
        self.memory_status()

    def _finish_file(self, job, task):
        item, process = task["item"], task["process"]
        if process.is_alive():
            try:
                for child in psutil.Process(process.pid).children(recursive=True):
                    child.kill()
            except psutil.Error:
                pass
            process.terminate()
        process.join(timeout=3)
        if process.is_alive():
            process.kill()
            process.join(timeout=3)
        task["connection"].close()
        process.close()
        with self.workspace.lock:
            item.setdefault("memory", {}).update(
                {
                    "budget_bytes": task["budget"],
                    "peak_rss_bytes": task.get("peak_rss", 0),
                    "waiting": False,
                }
            )
            if task["result"] and self.output_path(job, item).is_file():
                transition(item, "succeeded", file=True)
                item.update(task["result"])
                upload = self.uploads.items[item["upload_id"]]
                item.setdefault(
                    "source_bytes", item.get("entry", {}).get("size_bytes", upload["size_bytes"])
                )
                item["savings_percent"] = (
                    100 * (item["source_bytes"] - item["size_bytes"]) / item["source_bytes"]
                )
            elif self._cancelled(job):
                transition(item, "cancelled", file=True)
            else:
                transition(item, "failed", file=True)
                item["error"] = task["error"] or "Conversion worker exited unexpectedly."
            if item["state"] != "succeeded":
                self.output_path(job, item).unlink(missing_ok=True)
                for thumbnail in (False, True):
                    self.preview_path(job, item, thumbnail).unlink(missing_ok=True)
            for kind in ("preview", "thumbnail"):
                for extension in (".jpg", ".png"):
                    derivative = self.directory(job) / (item["output_id"] + f".{kind}{extension}")
                    derivative.with_suffix(extension + ".part").unlink(missing_ok=True)
                    if item["state"] != "succeeded" or not item.get("preview"):
                        derivative.unlink(missing_ok=True)
            output = self.output_path(job, item)
            output.with_suffix(output.suffix + ".part").unlink(missing_ok=True)
            self._clear_document_scratch(job, item)
            if task["staged"]:
                task["staged"].unlink(missing_ok=True)
            self.workspace.release(item["id"])
            self.save(job)

    def _supervise(self, job, pending):
        active = {}
        cleanup_at = time.monotonic() + self.settings.cleanup_seconds
        memory_at = admission_at = 0.0
        try:
            while pending or active:
                if time.monotonic() >= cleanup_at:
                    self.cleanup()
                    cleanup_at = time.monotonic() + self.settings.cleanup_seconds
                if self._cancelled(job):
                    with self.workspace.lock:
                        while pending:
                            transition(pending.popleft(), "cancelled", file=True)
                admission_due = time.monotonic() >= admission_at
                while (
                    pending
                    and admission_due
                    and len(active) < job["settings"]["concurrency"]
                    and not self._cancelled(job)
                ):
                    item = pending[0]
                    try:
                        if not self._start_file(job, item, active):
                            break
                        pending.popleft()
                    except (Problem, ValueError, OSError) as exc:
                        pending.popleft()
                        with self.workspace.lock:
                            transition(
                                item, "cancelled" if self._cancelled(job) else "failed", file=True
                            )
                            item["error"] = (
                                str(exc)
                                if isinstance(exc, (Problem, ValueError))
                                else "File staging failed."
                            )
                        self.save(job)
                if admission_due:
                    admission_at = time.monotonic() + self.settings.memory_poll_seconds
                if time.monotonic() >= memory_at:
                    self._check_memory(job, active)
                    memory_at = time.monotonic() + self.settings.memory_poll_seconds
                    try:
                        self.workspace.check_capacity()
                    except Problem:
                        for task in active.values():
                            task["error"] = "Workspace capacity exhausted during conversion."
                for identifier, task in list(active.items()):
                    process = task["process"]
                    self._collect_messages(job, task, active)
                    now = time.monotonic()
                    if self._cancelled(job) and task["cancel_at"] is None:
                        task["stop"].set()
                        task["cancel_at"] = now
                    if now - task["started"] > self.settings.file_timeout_seconds:
                        task["error"] = "Image conversion timed out."
                    cancelled = (
                        task["cancel_at"] is not None
                        and now - task["cancel_at"] >= self.settings.cancel_grace_seconds
                    )
                    exited = not process.is_alive()
                    if exited:
                        # The child can send its result and exit between our first poll
                        # and is_alive(). Drain once more before classifying that exit.
                        self._collect_messages(job, task, active)
                    if task["error"] or cancelled or exited:
                        self._finish_file(job, task)
                        del active[identifier]
                        admission_at = memory_at = 0.0
                self.stop.wait(0.1) if not self.stop.is_set() else time.sleep(0.01)
        finally:
            for task in active.values():
                task["error"] = "Host stopped while converting."
                self._finish_file(job, task)
            self._conversion_workers = 0
            self._pressure_since = None

    def _run_job(self, job):
        if job["state"] in JOB_TERMINAL:
            return
        if job["state"] == "queued":
            with self.workspace.lock:
                transition(job, "inspecting")
            self.save(job)
            self._inspect(job)
        if not self._cancelled(job):
            with self.workspace.lock:
                transition(job, "converting")
            self.save(job)
        self._supervise(job, deque(item for item in job["files"] if item["state"] == "queued"))
        if self.stop.is_set():
            with self.workspace.lock:
                transition(job, "interrupted")
                job["expires_at"] = time.time() + self.settings.retention_seconds
                self.save(job)
            return
        if job["state"] != "cancelling":
            with self.workspace.lock:
                transition(job, "packaging")
        successes = [item for item in job["files"] if item["state"] == "succeeded"]
        self.save(job)
        if successes:
            key = "package-" + job["id"]
            try:
                total = (
                    sum(
                        self.output_path(job, item).stat().st_size
                        + 2 * len(item["output_name"].encode("utf-8"))
                        + 256
                        for item in successes
                    )
                    + MiB
                )
                self.workspace.reserve(key, total)
                package_outputs(
                    self.archive_path(job),
                    [
                        {"path": self.output_path(job, item), "output_name": item["output_name"]}
                        for item in successes
                    ],
                    lambda n: self.workspace.consume(key, n),
                    self.stop.is_set,
                )
                job["package_status"] = "ready"
            except (Problem, ValueError, OSError):
                job["package_status"] = "failed"
                job["warnings"].append(
                    "Result ZIP could not be completed; individual files remain available."
                )
            finally:
                self.workspace.release(key)
        else:
            job["package_status"] = "unavailable"
        with self.workspace.lock:
            if self.stop.is_set():
                terminal = "interrupted"
            elif job["state"] == "cancelling":
                terminal = "cancelled"
            elif not successes:
                terminal = "failed"
            elif counters(job)["failed"] or job["package_status"] == "failed":
                terminal = "completed_with_errors"
            else:
                terminal = "completed"
            transition(job, terminal)
            job["expires_at"] = time.time() + self.settings.retention_seconds
            self.save(job)
