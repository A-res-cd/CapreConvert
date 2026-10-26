"""Validated resource defaults; all byte units are binary."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

MiB = 1024**2
GiB = 1024**3
PREVIEW_MAX_BYTES = 2 * MiB
THUMBNAIL_MAX_BYTES = 256 * 1024


def default_workspace() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return base / "LocalRAW" / "workspace"


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace: Path = Field(default_factory=default_workspace)
    port: int = Field(default=8765, ge=1024, le=65535)
    lan: bool = False
    allowed_hosts: list[str] = Field(default_factory=list)
    tls_cert: Path | None = None
    tls_key: Path | None = None
    raw_max_bytes: int = Field(default=512 * MiB, gt=0)
    zip_max_bytes: int = Field(default=4 * GiB, gt=0)
    raster_max_bytes: int = Field(default=64 * MiB, gt=0)
    raster_output_max_bytes: int = Field(default=256 * MiB, gt=0)
    raster_max_dimension: int = Field(default=32768, ge=1, le=65535)
    raster_header_max_bytes: int = Field(default=2 * MiB, gt=0, le=16 * MiB)
    preview_memory_bytes: int = Field(default=384 * MiB, ge=256 * MiB)
    preview_timeout_seconds: float = Field(default=30, gt=0)
    preview_max_pages: int = Field(default=300, ge=1, le=5000)
    preview_max_edge: int = Field(default=1280, ge=128, le=2048)
    preview_max_pixels: int = Field(default=2_000_000, ge=1, le=4_194_304)
    preview_max_bytes: int = Field(default=2 * MiB, gt=0, le=8 * MiB)
    preview_text_characters: int = Field(default=50000, ge=1, le=100000)
    preview_table_cells: int = Field(default=1000, ge=1, le=5000)
    preview_pending_requests: int = Field(default=4, ge=1, le=16)
    document_max_bytes: int = Field(default=64 * MiB, gt=0)
    document_output_max_bytes: int = Field(default=128 * MiB, gt=0)
    document_expanded_max_bytes: int = Field(default=256 * MiB, gt=0)
    document_max_pages: int = Field(default=300, ge=1, le=5000)
    document_max_characters: int = Field(default=2_000_000, ge=1)
    pdf_page_content_max_bytes: int = Field(default=16 * MiB, gt=0)
    document_memory_bytes: int = Field(default=768 * MiB, ge=256 * MiB)
    job_upload_max_bytes: int = Field(default=8 * GiB, gt=0)
    max_files: int = Field(default=500, ge=1, le=10000)
    zip_max_entries: int = Field(default=10000, ge=1)
    zip_directory_max_bytes: int = Field(default=32 * MiB, gt=0)
    zip_lzma_dictionary_max_bytes: int = Field(default=64 * MiB, ge=4096, le=64 * MiB)
    expanded_max_bytes: int = Field(default=16 * GiB, gt=0)
    compression_ratio: float = Field(default=200, ge=1)
    max_pixels: int = Field(default=120_000_000, ge=1, le=120_000_000)
    default_concurrency: int = Field(default=1, ge=1, le=2)
    max_concurrency: int = Field(default=2, ge=1, le=2)
    session_pending_jobs: int = Field(default=3, ge=1)
    global_pending_jobs: int = Field(default=10, ge=1)
    workspace_quota_bytes: int = Field(default=30 * GiB, gt=0)
    min_free_bytes: int = Field(default=2 * GiB, ge=0)
    memory_reserve_bytes: int = Field(default=768 * MiB, ge=256 * MiB)
    worker_memory_bytes: int | None = Field(default=None, ge=256 * MiB)
    memory_poll_seconds: float = Field(default=0.5, ge=0.25, le=5)
    file_timeout_seconds: float = Field(default=300, gt=0)
    cancel_grace_seconds: float = Field(default=2, ge=0, le=10)
    upload_expiry_seconds: int = Field(default=3600, ge=1)
    retention_seconds: int = Field(default=86400, ge=1)
    cleanup_seconds: int = Field(default=600, ge=1)
    session_expiry_seconds: int = Field(default=7 * 86400, ge=3600)
    max_uploads_per_session: int = Field(default=1000, ge=1)
    max_sessions: int = Field(default=100, ge=1)
    export_cache_per_job: int = Field(default=3, ge=1, le=20)
    exiftool: Path | None = None
    libreoffice: Path | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.default_concurrency > self.max_concurrency:
            raise ValueError("default concurrency exceeds maximum")
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ValueError("TLS requires both certificate and key")
        self.workspace = self.workspace.expanduser().resolve()
        return self

    @classmethod
    def load(cls, config_file: Path | None = None, **overrides):
        values = json.loads(config_file.read_text("utf-8")) if config_file else {}
        for field in cls.model_fields:
            value = os.environ.get("LOCALRAW_" + field.upper())
            if value is not None:
                try:
                    values[field] = json.loads(value)
                except json.JSONDecodeError:
                    values[field] = value
        values.update({key: value for key, value in overrides.items() if value is not None})
        return cls.model_validate(values)
