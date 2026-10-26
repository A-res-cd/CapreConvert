"""Immutable input contracts and explicit state transitions."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .formats import ConversionKind

JOB_TERMINAL = {"completed", "completed_with_errors", "cancelled", "failed", "interrupted"}
FILE_TERMINAL = {"succeeded", "failed", "skipped", "cancelled"}
JOB_TRANSITIONS = {
    "queued": {"inspecting", "cancelling", "interrupted", "failed"},
    "inspecting": {"converting", "packaging", "cancelling", "failed", "interrupted"},
    "converting": {"packaging", "cancelling", "failed", "interrupted"},
    "packaging": {"completed", "completed_with_errors", "failed", "cancelling", "interrupted"},
    "cancelling": {"cancelled", "interrupted"},
}
FILE_TRANSITIONS = {
    "queued": {"extracting", "decoding", "skipped", "failed", "cancelled"},
    "extracting": {"decoding", "failed", "cancelled"},
    "decoding": {"encoding", "failed", "cancelled"},
    "encoding": {"validating", "failed", "cancelled"},
    "validating": {"succeeded", "failed", "cancelled"},
}


def transition(record, state, *, file=False):
    if record["state"] == state:
        return
    transitions = FILE_TRANSITIONS if file else JOB_TRANSITIONS
    if state not in transitions.get(record["state"], set()):
        raise ValueError(f"Illegal state transition: {record['state']} -> {state}")
    record["state"] = state


class RasterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    preset: Literal["smaller", "balanced", "high"] = "balanced"
    max_width: int | None = Field(default=None, ge=1, le=32768)
    max_height: int | None = Field(default=None, ge=1, le=32768)
    jpeg_quality: int | None = Field(default=None, ge=70, le=100)
    webp_quality: int | None = Field(default=None, ge=1, le=100)
    webp_lossless: bool = False
    png_compression: int | None = Field(default=None, ge=0, le=9)
    background: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")


class ConversionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    raster: RasterSettings = Field(default_factory=RasterSettings)
    conversion: ConversionKind = "cr3_to_jpg"
    jpeg_quality: int = Field(default=95, ge=70, le=100)
    filename_suffix: str = Field(default="", max_length=40)
    white_balance: Literal["camera", "auto"] = "camera"
    preserve_metadata: bool = True
    include_gps: bool = False
    concurrency: int = Field(default=1, ge=1, le=2)

    @field_validator("filename_suffix")
    @classmethod
    def safe_suffix(cls, value):
        if value and not re.fullmatch(r"[\w -]+", value, flags=re.UNICODE):
            raise ValueError("Suffix can contain letters, numbers, spaces, underscores and hyphens.")
        return value


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=240)
    size_bytes: int = Field(gt=0)


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_ids: list[str] = Field(min_length=1, max_length=500)
    settings: ConversionSettings = Field(default_factory=ConversionSettings)

    @field_validator("upload_ids")
    @classmethod
    def unique_ids(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Upload IDs must be unique.")
        return values


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: str = Field(min_length=1, max_length=256)


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    output_ids: list[str] = Field(min_length=1, max_length=10000)

    @field_validator("output_ids")
    @classmethod
    def unique_outputs(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Select each output only once.")
        return values
