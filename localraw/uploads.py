"""Owned staged binary uploads. Retry always starts a new partial file."""

import asyncio
import json
import os
import time
from pathlib import PurePosixPath

from .archives import safe_filename
from .errors import Problem
from .storage import atomic_json, opaque_id, valid_id


class Uploads:
    def __init__(self, workspace, settings):
        self.workspace, self.settings = workspace, settings
        self.items = {}
        for path in (workspace.root / "manifests").glob("upload-*.json"):
            try:
                item = json.loads(path.read_text("utf-8"))
                if (
                    item["id"] != path.stem.removeprefix("upload-")
                    or not valid_id(item["id"])
                    or not valid_id(item["owner"])
                    or item["size_bytes"] <= 0
                ):
                    continue
                item["refs"] = []  # Rebuilt from authoritative job manifests on startup.
                if item["state"] == "receiving":
                    item["state"] = "registered"
                if item["state"] == "ready" and (
                    not self.path(item).exists() or self.path(item).stat().st_size != item["size_bytes"]
                ):
                    item["state"] = "failed"
                self.items[item["id"]] = item
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def path(self, item):
        return self.workspace.root / "uploads" / (item["id"] + ".input")

    def save(self, item):
        atomic_json(self.workspace.manifest("upload", item["id"]), item)

    def owned(self, upload_id, owner):
        item = self.items.get(upload_id)
        if not item or item["owner"] != owner:
            raise Problem(404, "UPLOAD_NOT_FOUND", "Upload not found.")
        return item

    def register(self, owner, request):
        try:
            filename = safe_filename(request.filename)
        except ValueError as exc:
            raise Problem(
                422, "INVALID_FILENAME", "Choose a safe CR3, ZIP, DOCX, PDF, JPG, PNG or WebP filename."
            ) from exc
        extension = PurePosixPath(filename).suffix.lower()
        if extension not in {".cr3", ".zip", ".docx", ".pdf", ".jpg", ".jpeg", ".png", ".webp"}:
            raise Problem(
                422, "UNSUPPORTED_INPUT", "Supported inputs are CR3, ZIP, DOCX, PDF, JPG, PNG and WebP."
            )
        limit = (
            self.settings.zip_max_bytes
            if extension == ".zip"
            else self.settings.raw_max_bytes
            if extension == ".cr3"
            else self.settings.raster_max_bytes
            if extension in {".jpg", ".jpeg", ".png", ".webp"}
            else self.settings.document_max_bytes
        )
        if request.size_bytes > limit:
            raise Problem(413, "INPUT_TOO_LARGE", "Input exceeds its configured size limit.")
        with self.workspace.lock:
            owned = [item for item in self.items.values() if item["owner"] == owner]
            if len(owned) >= self.settings.max_uploads_per_session:
                raise Problem(
                    429, "UPLOAD_LIMIT", "Too many retained uploads. Delete old jobs or uploads."
                )
            identifier = opaque_id()
            self.workspace.reserve(identifier, request.size_bytes)
            item = {
                "id": identifier,
                "owner": owner,
                "filename": filename,
                "size_bytes": request.size_bytes,
                "state": "registered",
                "refs": [],
                "expires_at": time.time() + self.settings.upload_expiry_seconds,
            }
            try:
                self.save(item)
                self.items[identifier] = item
            except BaseException:
                self.workspace.release(identifier)
                raise
            return {"upload_id": identifier, "expires_at": item["expires_at"]}

    async def receive(self, owner, identifier, request):
        with self.workspace.lock:
            item = self.owned(identifier, owner)
            if item["refs"] or item["state"] in {"receiving", "ready"}:
                raise Problem(409, "UPLOAD_BUSY", "Upload is already ready or in use.")
            if item["expires_at"] < time.time():
                raise Problem(409, "UPLOAD_EXPIRED", "Upload expired. Register the file again.")
            self.workspace.release(identifier)
            self.workspace.reserve(identifier, item["size_bytes"])
            item["state"] = "receiving"
            self.save(item)
        partial = self.path(item).with_suffix(".input.part")
        count = 0
        try:
            with partial.open("wb") as stream:
                async for incoming in request.stream():
                    # ASGI chunk sizes are not trusted; each filesystem write is bounded.
                    for offset in range(0, len(incoming), 1024**2):
                        chunk = incoming[offset : offset + 1024**2]
                        count += len(chunk)
                        if count > item["size_bytes"]:
                            raise Problem(
                                413, "UPLOAD_TOO_LARGE", "Received more bytes than registered."
                            )
                        await asyncio.to_thread(stream.write, chunk)
                        await asyncio.to_thread(self.workspace.consume, identifier, len(chunk))
                if count != item["size_bytes"]:
                    raise Problem(
                        422, "INCOMPLETE_UPLOAD", "Uploaded byte count does not match registration."
                    )
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(partial, self.path(item))
            with self.workspace.lock:
                item["state"] = "ready"
                self.save(item)
            return {"upload_id": identifier, "state": "ready", "size_bytes": count}
        finally:
            partial.unlink(missing_ok=True)
            with self.workspace.lock:
                if item["state"] == "receiving":
                    item["state"] = "registered"
                    self.save(item)
                self.workspace.release(identifier)

    def delete(self, owner, identifier):
        with self.workspace.lock:
            item = self.owned(identifier, owner)
            if item["refs"] or item["state"] == "receiving":
                raise Problem(409, "UPLOAD_REFERENCED", "Upload is in use by a retained job or upload.")
            self.path(item).unlink(missing_ok=True)
            self.path(item).with_suffix(".input.part").unlink(missing_ok=True)
            self.workspace.manifest("upload", identifier).unlink(missing_ok=True)
            self.workspace.release(identifier)
            del self.items[identifier]

    def cleanup(self):
        with self.workspace.lock:
            for item in list(self.items.values()):
                if (
                    not item["refs"]
                    and item["state"] != "receiving"
                    and item["expires_at"] < time.time()
                ):
                    self.delete(item["owner"], item["id"])
