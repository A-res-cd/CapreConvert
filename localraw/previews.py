"""Committed-output derivatives; parsers/codecs import only in supervised child."""

import hashlib
import importlib.metadata
import json
import math
import os
import time
from contextlib import closing
from pathlib import Path

import psutil

from .config import MiB
from .errors import Problem
from .storage import atomic_json, file_hash

PREVIEW_REVISION = "v0.4-preview-1"


def cache_identity(item, kind, page, settings):
    renderer = "pypdfium2" if kind == "pdf" else "lxml" if kind == "docx" else "Pillow"
    options = {
        key: value
        for key, value in settings.model_dump(mode="json").items()
        if key.startswith("preview_")
    }
    value = [
        PREVIEW_REVISION,
        item.get("sha256"),
        kind,
        page,
        importlib.metadata.version(renderer),
        options,
    ]
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def render_worker(source, target, kind, page, limits, connection):
    try:
        from .errors import ConversionError
        from .raster import BoundedWriter

        path, target = Path(source), Path(target)
        part = target.with_suffix(target.suffix + ".part")
        if kind == "pdf":
            import pypdfium2 as pdfium
            from PIL import Image

            with pdfium.PdfDocument(str(path)) as document:
                count = len(document)
                if count < 1 or count > limits["preview_max_pages"] or not 1 <= page <= count:
                    raise ConversionError("PDF preview page is outside the supported page range.")
                with closing(document[page - 1]) as pdf_page:
                    width, height = pdf_page.get_size()
                    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
                        raise ConversionError("Invalid PDF page geometry.")
                    scale = min(
                        1.5,
                        limits["preview_max_edge"] / max(width, height),
                        math.sqrt(limits["preview_max_pixels"] / (width * height)),
                    )
                    # Round-up is part of PDFium's bitmap geometry.
                    if (
                        math.ceil(width * scale) * math.ceil(height * scale)
                        > limits["preview_max_pixels"]
                    ):
                        scale *= 0.99
                    with closing(pdf_page.render(scale=scale, may_draw_forms=False)) as bitmap:
                        with bitmap.to_pil() as pixels:
                            with pixels.convert("RGB") as image:
                                with part.open("wb") as stream:
                                    image.save(
                                        BoundedWriter(
                                            stream,
                                            part,
                                            limits["preview_max_bytes"],
                                            limits["min_free_bytes"],
                                        ),
                                        format="PNG",
                                        compress_level=3,
                                    )
                                dimensions = image.size
            with Image.open(part) as checked:
                checked.load()
                if checked.size != dimensions:
                    raise ConversionError("PDF preview validation failed.")
            details = {
                "kind": "pdf",
                "page": page,
                "pages": count,
                "width": dimensions[0],
                "height": dimensions[1],
            }
        elif kind == "docx":
            import zipfile

            from .documents import _validate_docx, _xml_root

            _validate_docx(path, limits, lambda: False, generated=True)
            with zipfile.ZipFile(path) as archive:
                main = archive.getinfo("word/document.xml")
                if main.file_size > min(limits["document_expanded_max_bytes"], 16 * MiB):
                    raise ConversionError("DOCX preview XML exceeds its byte limit.")
                root = _xml_root(archive.read(main))
            namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            body = root.find(namespace + "body")
            blocks, remaining, cells = (
                [],
                limits["preview_text_characters"],
                limits["preview_table_cells"],
            )
            truncated = False

            def text(element):
                nonlocal remaining, truncated
                chunks = []
                for node in element.iter(namespace + "t"):
                    value = node.text or ""
                    if len(value) > remaining:
                        value = value[:remaining]
                        truncated = True
                    chunks.append(value)
                    remaining -= len(value)
                    if remaining <= 0:
                        truncated = True
                        break
                return "".join(chunks)

            if body is not None:
                for child in body:
                    if remaining <= 0 or len(blocks) >= 500:
                        truncated = True
                        break
                    if child.tag == namespace + "p":
                        blocks.append({"type": "paragraph", "text": text(child)})
                    elif child.tag == namespace + "tbl":
                        rows = []
                        for row in child.findall(namespace + "tr"):
                            values = []
                            for cell in row.findall(namespace + "tc"):
                                if cells <= 0 or remaining <= 0:
                                    truncated = True
                                    break
                                values.append(text(cell))
                                cells -= 1
                            rows.append(values)
                            if truncated:
                                break
                        blocks.append({"type": "table", "rows": rows})
            details = {
                "kind": "docx",
                "blocks": blocks,
                "truncated": truncated,
                "notice": "Read-only content preview; not exact Word page layout.",
            }
            part.write_text(json.dumps(details, ensure_ascii=True), encoding="utf-8")
        elif kind == "image":
            from PIL import Image

            with Image.open(path) as image:
                if image.width * image.height > limits["max_pixels"]:
                    raise ConversionError("Preview exceeds the image pixel limit.")
                image.draft("RGB", (limits["preview_max_edge"], limits["preview_max_edge"]))
                image.thumbnail((limits["preview_max_edge"], limits["preview_max_edge"]))
                with image.convert("RGBA" if "A" in image.getbands() else "RGB") as reduced:
                    with part.open("wb") as stream:
                        reduced.save(
                            BoundedWriter(
                                stream, part, limits["preview_max_bytes"], limits["min_free_bytes"]
                            ),
                            format="PNG",
                            compress_level=3,
                        )
                    details = {"kind": "image", "width": reduced.width, "height": reduced.height}
        else:
            raise ConversionError("Preview unavailable for this format.")
        if not 0 < part.stat().st_size <= limits["preview_max_bytes"]:
            raise ConversionError("Preview exceeds its byte limit.")
        with part.open("rb+") as stream:
            os.fsync(stream.fileno())
        os.replace(part, target)
        connection.send({"details": details, "sha256": file_hash(target)})
    except Exception as exc:
        from .errors import ConversionError

        connection.send(
            {
                "error": str(exc)
                if isinstance(exc, ConversionError)
                else "Preview renderer failed safely. Direct download remains available."
            }
        )
    finally:
        connection.close()


def prepare(jobs, job, item, page=1):
    """Caller holds parent download lease; serialize with conversion and deduplicate caches."""
    from .formats import format_for

    settings, workspace = jobs.settings, jobs.workspace
    kind = format_for(job["settings"]).preview_kind
    if kind == "none":
        return {"kind": "none", "notice": "Preview unavailable for this format."}, None
    if kind != "pdf" and page != 1:
        raise Problem(422, "PREVIEW_PAGE", "This format has no page navigation.")
    if not jobs.preview_slots.acquire(blocking=False):
        raise Problem(429, "PREVIEW_BUSY", "Preview queue is full. Try again shortly.")
    acquired = False
    deadline = time.monotonic() + settings.preview_timeout_seconds
    try:
        while not acquired:
            if jobs.stop.is_set() or time.monotonic() > deadline:
                raise Problem(
                    503, "PREVIEW_BUSY", "Preview is waiting for conversion resources. Retry shortly."
                )
            acquired = jobs.execution_lock.acquire(timeout=0.1)
        identity = cache_identity(item, kind, page, settings)
        target = jobs.directory(job) / ("pv-" + identity + (".json" if kind == "docx" else ".png"))
        sidecar = target.with_suffix(target.suffix + ".meta")
        if (
            target.is_file()
            and sidecar.is_file()
            and target.stat().st_size <= settings.preview_max_bytes
            and sidecar.stat().st_size <= settings.preview_max_bytes
        ):
            try:
                cached = json.loads(sidecar.read_text("utf-8"))
                if (
                    isinstance(cached, dict)
                    and isinstance(cached.get("details"), dict)
                    and cached["details"].get("kind") == kind
                    and cached.get("output_id") == item["output_id"]
                    and cached.get("fingerprint") == identity
                    and cached.get("sha256") == file_hash(target)
                ):
                    return {**cached["details"], "cached": True}, target
            except (OSError, ValueError, KeyError, TypeError):
                pass
            sidecar.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
        if kind == "pdf" and page > settings.preview_max_pages:
            raise Problem(422, "PREVIEW_PAGE", "Page exceeds the configured preview limit.")
        budget = settings.preview_memory_bytes
        if kind == "image":
            budget = max(budget, 128 * MiB + item.get("width", 0) * item.get("height", 0) * 24)
        cap = settings.worker_memory_bytes
        if cap is not None and budget > cap:
            raise Problem(503, "PREVIEW_MEMORY", "Preview exceeds the configured worker memory limit.")
        if psutil.virtual_memory().available < budget + settings.memory_reserve_bytes:
            raise Problem(
                503,
                "PREVIEW_MEMORY",
                "Not enough available RAM for preview. Direct download remains available.",
            )
        key = "preview-" + identity
        workspace.reserve(key, 2 * settings.preview_max_bytes)
        parent, child = jobs.context.Pipe()
        process = jobs.context.Process(
            target=render_worker,
            args=(
                str(jobs.output_path(job, item)),
                str(target),
                kind,
                page,
                settings.model_dump(mode="json"),
                child,
            ),
            name="capreconvert-preview",
        )
        result = None
        try:
            process.start()
            child.close()
            started = time.monotonic()
            pressure = None
            while result is None:
                try:
                    if parent.poll(0.05):
                        result = parent.recv()
                except (EOFError, OSError):
                    break
                if result is not None:
                    break
                if not process.is_alive():
                    break
                try:
                    rss = psutil.Process(process.pid).memory_info().rss
                except psutil.NoSuchProcess:
                    continue
                available = psutil.virtual_memory().available
                if available < settings.memory_reserve_bytes:
                    pressure = pressure or time.monotonic()
                else:
                    pressure = None
                if (
                    jobs.stop.is_set()
                    or rss > budget
                    or time.monotonic() - started > settings.preview_timeout_seconds
                    or available < 256 * MiB
                    or (pressure and time.monotonic() - pressure >= 1)
                ):
                    raise Problem(
                        503,
                        "PREVIEW_LIMIT",
                        "Preview stopped at its resource/time limit. Direct download remains available.",
                    )
                workspace.check_capacity()
            process.join(timeout=1)
            if not result or "error" in result or not target.is_file():
                raise Problem(
                    422,
                    "PREVIEW_FAILED",
                    (result or {}).get(
                        "error", "Preview worker exited. Direct download remains available."
                    ),
                )
            result.update(output_id=item["output_id"], fingerprint=identity)
            atomic_json(sidecar, result)
            return {**result["details"], "cached": False}, target
        finally:
            if process.pid and process.is_alive():
                process.terminate()
                process.join(timeout=3)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=3)
            if process.pid:
                process.close()
            parent.close()
            child.close()
            target.with_suffix(target.suffix + ".part").unlink(missing_ok=True)
            if not sidecar.is_file():
                target.unlink(missing_ok=True)
            workspace.release(key)
    finally:
        if acquired:
            jobs.execution_lock.release()
        jobs.preview_slots.release()
