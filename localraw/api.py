"""Thin authenticated HTTP handlers; attachment responses retain deletion leases."""

import copy
import importlib.metadata
from dataclasses import asdict
from pathlib import PurePosixPath

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from . import APP_NAME, __version__
from .errors import Problem
from .formats import CONVERSIONS, FORMATS, format_for
from .jobs import public_file, public_job
from .metadata import executable
from .models import ExportRequest, JobRequest, SessionRequest, UploadRequest
from .security import COOKIE

router = APIRouter(prefix="/api/v1")


def owner(request):
    return request.state.session["owner"]


def page(items, offset, limit):
    return {
        "items": items[offset : offset + limit],
        "total": len(items),
        "offset": offset,
        "limit": limit,
    }


class Download(FileResponse):
    """Release even if a browser disconnects before a background callback could run."""

    def __init__(self, path, lease, **kwargs):
        self.lease = lease
        super().__init__(path, **kwargs)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.lease.__exit__(None, None, None)


@router.post("/sessions")
def sessions(body: SessionRequest, request: Request):
    token, session = request.app.state.security.exchange(body.credential, request.client.host)
    response = JSONResponse({"csrf_token": session["csrf"], "expires_at": session["expires"]})
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=bool(request.app.state.settings.tls_cert),
        max_age=request.app.state.settings.session_expiry_seconds,
        path="/",
    )
    return response


@router.get("/sessions")
def current_session(request: Request):
    return {"csrf_token": request.state.session["csrf"], "expires_at": request.state.session["expires"]}


@router.get("/capabilities")
def capabilities(request: Request):
    import rawpy

    from .documents import libreoffice_executable

    settings = request.app.state.settings
    limits = settings.model_dump(
        mode="json",
        exclude={"workspace", "tls_key", "tls_cert", "exiftool", "libreoffice", "allowed_hosts"},
    )
    office_available = bool(libreoffice_executable(settings.libreoffice))
    conversions = []
    for descriptor in CONVERSIONS.values():
        available = descriptor.id != "docx_to_pdf" or office_available
        conversions.append(
            {
                **asdict(descriptor),
                "available": available,
                "settings_fields": ["raster", "preserve_metadata", "include_gps"]
                if descriptor.engine == "raster"
                else ["jpeg_quality", "white_balance", "preserve_metadata", "include_gps"]
                if descriptor.engine == "raw"
                else [],
                "selection_export": "one_direct_multiple_zip",
                "setup_message": None
                if available
                else "Install LibreOffice on this computer and restart CapreConvert.",
                "limitations": [
                    "Text-based PDFs only; no OCR. Paragraphs are editable; complex layouts may change."
                ]
                if descriptor.id == "pdf_to_docx"
                else [],
            }
        )
    return {
        "application_name": APP_NAME,
        "application_version": __version__,
        "rawpy_version": rawpy.__version__,
        "libraw_version": ".".join(map(str, rawpy.libraw_version)),
        "decoder_features": rawpy.flags,
        "pillow_version": importlib.metadata.version("Pillow"),
        "supported_extensions": sorted(
            {extension for entry in CONVERSIONS.values() for extension in entry.input_extensions}
        ),
        "conversions": conversions,
        "formats": list(FORMATS.values()),
        "limits": limits,
        "metadata_available": bool(executable(settings.exiftool)),
        "camera_compatibility": "Support varies by camera and recording mode; validate representative originals.",
    }


@router.get("/resources")
def resources(request: Request):
    return request.app.state.jobs.memory_status()


@router.post("/uploads", status_code=201)
def register_upload(body: UploadRequest, request: Request):
    return request.app.state.uploads.register(owner(request), body)


@router.put("/uploads/{upload_id}/content")
async def upload_content(upload_id: str, request: Request):
    return await request.app.state.uploads.receive(owner(request), upload_id, request)


@router.delete("/uploads/{upload_id}", status_code=204)
def delete_upload(upload_id: str, request: Request):
    request.app.state.uploads.delete(owner(request), upload_id)
    return Response(status_code=204)


@router.post("/jobs", status_code=202)
def create_job(body: JobRequest, request: Request, idempotency_key: str | None = Header(default=None)):
    return request.app.state.jobs.create(owner(request), body, idempotency_key)


@router.get("/jobs")
def jobs(request: Request, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)):
    with request.app.state.workspace.lock:
        items = [
            public_job(job)
            for job in request.app.state.jobs.items.values()
            if job["owner"] == owner(request)
        ]
        items.sort(key=lambda job: job["created_at"], reverse=True)
        return page(items, offset, limit)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    with request.app.state.workspace.lock:
        return public_job(request.app.state.jobs.owned(job_id, owner(request)))


@router.get("/jobs/{job_id}/files")
def files(
    job_id: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    with request.app.state.workspace.lock:
        job = request.app.state.jobs.owned(job_id, owner(request))
        return page([public_file(item) for item in job["files"]], offset, limit)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    return request.app.state.jobs.cancel(owner(request), job_id)


@router.get("/jobs/{job_id}/errors")
def errors(
    job_id: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)
):
    with request.app.state.workspace.lock:
        job = request.app.state.jobs.owned(job_id, owner(request))
        messages = [
            {
                "file_id": item["id"],
                "filename": item["name"],
                "error": item["error"],
                "warnings": list(item["warnings"]),
            }
            for item in job["files"]
            if item["error"] or item["warnings"]
        ]
        messages.extend(
            {"file_id": None, "filename": None, "error": None, "warnings": [warning]}
            for warning in job["warnings"]
        )
        return page(messages, offset, limit)


@router.get("/jobs/{job_id}/summary")
def summary(job_id: str, request: Request):
    with request.app.state.workspace.lock:
        job = request.app.state.jobs.owned(job_id, owner(request))
        report = public_job(job)
        report["files"] = [public_file(item) for item in job["files"]]
        report["retry_upload_ids"] = copy.copy(job["upload_ids"])
    return JSONResponse(
        report, headers={"Content-Disposition": 'attachment; filename="conversion-summary.json"'}
    )


@router.get("/jobs/{job_id}/results/{output_id}")
def download_output(job_id: str, output_id: str, request: Request):
    workspace, jobs = request.app.state.workspace, request.app.state.jobs
    with workspace.lock:
        job = jobs.owned(job_id, owner(request))
        item = next(
            (
                item
                for item in job["files"]
                if item["output_id"] == output_id and item["state"] == "succeeded"
            ),
            None,
        )
        if not item or not jobs.output_path(job, item).is_file():
            raise Problem(404, "RESULT_NOT_FOUND", "Successful result not found.")
        lease = workspace.downloading(job_id)
        lease.__enter__()
        return Download(
            jobs.output_path(job, item),
            lease,
            media_type=format_for(job["settings"]).media_type,
            filename=PurePosixPath(item["output_name"]).name,
        )


@router.get("/jobs/{job_id}/previews/{output_id}")
def preview_output(job_id: str, output_id: str, request: Request, thumbnail: bool = False):
    workspace, jobs = request.app.state.workspace, request.app.state.jobs
    with workspace.lock:
        job = jobs.owned(job_id, owner(request))
        item = next(
            (
                item
                for item in job["files"]
                if item["output_id"] == output_id and item["state"] == "succeeded"
            ),
            None,
        )
        if not item or not item.get("preview") or not jobs.preview_path(job, item, thumbnail).is_file():
            raise Problem(
                404,
                "PREVIEW_NOT_FOUND",
                "Preview unavailable. The original converted result may still be downloaded.",
            )
        lease = workspace.downloading(job_id)
        lease.__enter__()
        return Download(
            jobs.preview_path(job, item, thumbnail),
            lease,
            media_type="image/png"
            if jobs.preview_path(job, item, thumbnail).suffix == ".png"
            else "image/jpeg",
            filename="preview" + jobs.preview_path(job, item, thumbnail).suffix,
            content_disposition_type="inline",
        )


@router.get("/jobs/{job_id}/output-preview/{output_id}")
def output_preview(job_id: str, output_id: str, request: Request, page: int = Query(1, ge=1)):
    from .previews import prepare

    jobs, workspace = request.app.state.jobs, request.app.state.workspace
    with workspace.lock:
        job = jobs.owned(job_id, owner(request))
        item = next(
            (
                item
                for item in job["files"]
                if item["output_id"] == output_id and item["state"] == "succeeded"
            ),
            None,
        )
        if not item or not jobs.output_path(job, item).is_file():
            raise Problem(404, "RESULT_NOT_FOUND", "Successful result not found.")
        lease = workspace.downloading(job_id)
        lease.__enter__()
    try:
        details, path = prepare(jobs, job, item, page)
        if path and details["kind"] in {"image", "pdf"}:
            return Download(
                path,
                lease,
                media_type="image/png",
                filename="output-preview.png",
                content_disposition_type="inline",
                headers={
                    "X-Preview-Pages": str(details.get("pages", 1)),
                    "X-Preview-Cached": str(details["cached"]).lower(),
                },
            )
        lease.__exit__(None, None, None)
        return details
    except BaseException:
        lease.__exit__(None, None, None)
        raise


@router.post("/jobs/{job_id}/exports", status_code=201)
def prepare_selected_export(job_id: str, body: ExportRequest, request: Request):
    return request.app.state.jobs.prepare_export(owner(request), job_id, body.output_ids)


@router.get("/jobs/{job_id}/exports/{export_id}")
def download_selected_export(job_id: str, export_id: str, request: Request):
    workspace, jobs = request.app.state.workspace, request.app.state.jobs
    with workspace.lock:
        job = jobs.owned(job_id, owner(request))
        export = next((item for item in job.get("exports", []) if item["id"] == export_id), None)
        if not export or not jobs.export_path(job, export).is_file():
            raise Problem(
                404,
                "EXPORT_NOT_FOUND",
                "Prepared selection not found. Select the results and export again.",
            )
        lease = workspace.downloading(job_id)
        lease.__enter__()
        return Download(
            jobs.export_path(job, export),
            lease,
            media_type="application/zip",
            filename="CapreConvert-selected-results.zip",
        )


@router.get("/jobs/{job_id}/archive")
def download_archive(job_id: str, request: Request):
    workspace, jobs = request.app.state.workspace, request.app.state.jobs
    with workspace.lock:
        job = jobs.owned(job_id, owner(request))
        if job["package_status"] != "ready" or not jobs.archive_path(job).is_file():
            raise Problem(
                409,
                "ARCHIVE_NOT_READY",
                "Result ZIP is not ready; individual successes may be available.",
            )
        lease = workspace.downloading(job_id)
        lease.__enter__()
        return Download(
            jobs.archive_path(job),
            lease,
            media_type="application/zip",
            filename="CapreConvert-results.zip",
        )


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, request: Request):
    request.app.state.jobs.delete(owner(request), job_id)
    return Response(status_code=204)
