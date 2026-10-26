"""Validated conversion identities shared by jobs, engines and public capabilities."""

from dataclasses import dataclass, replace
from typing import Literal

ConversionKind = Literal[
    "cr3_to_jpg",
    "cr3_to_png",
    "docx_to_pdf",
    "pdf_to_docx",
    "jpg_to_png",
    "png_to_jpg",
    "jpg_to_webp",
    "png_to_webp",
    "webp_to_jpg",
    "webp_to_png",
    "jpg_to_jpg",
    "png_to_png",
    "webp_to_webp",
]


@dataclass(frozen=True)
class ConversionFormat:
    id: str
    label: str
    input_extensions: tuple[str, ...]
    output_extension: str
    media_type: str
    is_raw: bool
    engine: str = "document"
    preview_kind: str = "none"
    archive_input: bool = False
    direct_export: bool = True
    source_format: str = ""
    target_format: str = ""

    @property
    def is_image(self):
        return self.engine in {"raw", "raster"}


FORMATS = {
    "jpg": {"id": "jpg", "label": "JPG / JPEG", "short_label": "JPG", "category": "images"},
    "png": {"id": "png", "label": "PNG", "short_label": "PNG", "category": "images"},
    "webp": {"id": "webp", "label": "WebP", "short_label": "WebP", "category": "images"},
    "cr3": {"id": "cr3", "label": "Canon RAW (.CR3)", "short_label": "CR3", "category": "images"},
    "docx": {"id": "docx", "label": "DOCX", "short_label": "DOCX", "category": "documents"},
    "pdf": {"id": "pdf", "label": "PDF", "short_label": "PDF", "category": "documents"},
}


CONVERSIONS = {
    "cr3_to_jpg": ConversionFormat(
        "cr3_to_jpg", "CR3 → JPG", (".cr3", ".zip"), ".jpg", "image/jpeg", True, "raw", "image", True
    ),
    "cr3_to_png": ConversionFormat(
        "cr3_to_png", "CR3 → PNG", (".cr3", ".zip"), ".png", "image/png", True, "raw", "image", True
    ),
    "docx_to_pdf": ConversionFormat(
        "docx_to_pdf", "DOCX → PDF", (".docx",), ".pdf", "application/pdf", False, "document", "pdf"
    ),
    "pdf_to_docx": ConversionFormat(
        "pdf_to_docx",
        "PDF → DOCX",
        (".pdf",),
        ".docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        False,
        "document",
        "docx",
    ),
}


for key, source_id, target_id in (
    ("cr3_to_jpg", "cr3", "jpg"),
    ("cr3_to_png", "cr3", "png"),
    ("docx_to_pdf", "docx", "pdf"),
    ("pdf_to_docx", "pdf", "docx"),
):
    CONVERSIONS[key] = replace(CONVERSIONS[key], source_format=source_id, target_format=target_id)


for source, target in (
    ("jpg", "png"),
    ("png", "jpg"),
    ("jpg", "webp"),
    ("png", "webp"),
    ("webp", "jpg"),
    ("webp", "png"),
    ("jpg", "jpg"),
    ("png", "png"),
    ("webp", "webp"),
):
    key = f"{source}_to_{target}"
    CONVERSIONS[key] = ConversionFormat(
        key,
        f"{source.upper()} \u2192 {target.upper()}",
        (".jpg", ".jpeg") if source == "jpg" else (f".{source}",),
        f".{target}",
        "image/jpeg" if target == "jpg" else f"image/{target}",
        False,
        "raster",
        "image",
        source_format=source,
        target_format=target,
    )


def format_for(settings):
    key = settings.get("conversion", "cr3_to_jpg") if isinstance(settings, dict) else settings.conversion
    return CONVERSIONS[key]


def output_budget(pixels, extension):
    return pixels * (4 if extension == ".png" else 3) + 1024**2
