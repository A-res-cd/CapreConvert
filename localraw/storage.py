"""Private workspace ownership, atomic manifests and capacity reservations."""

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .errors import Problem


def opaque_id() -> str:
    return uuid.uuid4().hex


def valid_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{32}", value) is not None


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def private_directory(path):
    if os.name != "nt":
        path.chmod(0o700)
        return
    import csv
    import subprocess

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    account = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
        creationflags=flags,
    )
    sid = next(csv.reader(account.stdout.splitlines()))[1]
    if not re.fullmatch(r"S-1-[0-9-]+", sid):
        raise RuntimeError("Could not determine Windows workspace owner.")
    # Reset only the dedicated root's DACL, then retain this user and SYSTEM.
    for arguments in (
        ["/reset"],
        ["/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"],
    ):
        subprocess.run(
            ["icacls", str(path), *arguments],
            capture_output=True,
            check=True,
            timeout=10,
            creationflags=flags,
        )


def atomic_json(path: Path, value):
    temporary = path.with_name(path.name + ".part")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        # Windows sync/indexing/AV readers may briefly deny replacement. Keep the
        # existing manifest intact and retry only this atomic rename, never rewriting it.
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if os.name != "nt" or attempt == 5:
                    raise
                time.sleep(0.02 * 2**attempt)
    finally:
        temporary.unlink(missing_ok=True)


class Workspace:
    def __init__(self, settings):
        self.settings = settings
        self.root = settings.workspace
        self.lock = threading.RLock()
        self.reservations: dict[str, int] = {}
        self.downloads: dict[str, int] = {}
        self.handle = None

    def open(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker = self.root / ".localraw-workspace"
        if not marker.exists() and any(self.root.iterdir()):
            raise RuntimeError("Choose an empty, dedicated CapreConvert workspace directory.")
        self.handle = (self.root / "workspace.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                if self.handle.read(1) == b"":
                    self.handle.write(b"0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            self.handle = None
            raise RuntimeError(
                "Workspace already in use by another CapreConvert or legacy LocalRAW process."
            ) from exc
        try:
            if not marker.exists():
                private_directory(self.root)
                marker.write_text("LocalRAW workspace v1\n", encoding="ascii")
            for directory in ("uploads", "jobs", "manifests"):
                (self.root / directory).mkdir(mode=0o700, exist_ok=True)
            for partial in self.root.rglob("*.part"):
                partial.unlink(missing_ok=True)
        except BaseException:
            self.close()
            raise
        return self

    def close(self):
        if self.handle:
            self.handle.close()
            self.handle = None

    def used_bytes(self) -> int:
        total = 0
        for path in self.root.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except FileNotFoundError:
                pass  # A supervised worker may have just committed or removed a partial.
        return total

    def reserve(self, key: str, size: int):
        with self.lock:
            self.check_capacity(size)
            self.reservations[key] = self.reservations.get(key, 0) + size

    def check_capacity(self, additional: int = 0):
        with self.lock:
            reserved = sum(self.reservations.values())
            if self.used_bytes() + reserved + additional > self.settings.workspace_quota_bytes:
                raise Problem(507, "WORKSPACE_CAPACITY", "Not enough workspace capacity.")
            if shutil.disk_usage(self.root).free < self.settings.min_free_bytes + reserved + additional:
                raise Problem(507, "INSUFFICIENT_DISK_SPACE", "Not enough free workspace space.")

    def consume(self, key: str, size: int):
        with self.lock:
            self.reservations[key] = max(0, self.reservations.get(key, 0) - size)
            self.check_capacity()

    def release(self, key: str):
        with self.lock:
            self.reservations.pop(key, None)

    @contextmanager
    def downloading(self, job_id):
        with self.lock:
            self.downloads[job_id] = self.downloads.get(job_id, 0) + 1
        try:
            yield
        finally:
            with self.lock:
                self.downloads[job_id] -= 1
                if not self.downloads[job_id]:
                    del self.downloads[job_id]

    def manifest(self, kind, identifier) -> Path:
        return self.root / "manifests" / f"{kind}-{identifier}.json"
