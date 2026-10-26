"""Explicit UI worker doubles; browser routing is not document/RAW engine validation."""

from pathlib import Path


def ui_conversion_worker(source, destination, settings, limits, connection, stop):
    conversion = settings.get("conversion", "cr3_to_jpg")
    if conversion == "cr3_to_jpg":
        from tests.support import controlled_worker

        return controlled_worker(source, destination, settings, limits, connection, stop)
    if conversion == "cr3_to_png":
        from tests.integration.test_formats import png_decoder_double_worker

        return png_decoder_double_worker(source, destination, settings, limits, connection, stop)
    from localraw.formats import format_for

    if format_for(settings).engine == "raster":
        from localraw.worker import run_worker

        return run_worker(source, destination, settings, limits, connection, stop)
    try:
        from localraw.storage import file_hash

        connection.send({"stage": "decoding"})
        connection.send({"pixels": 1})
        if not connection.recv()["admitted"]:
            return
        connection.send({"stage": "encoding"})
        if conversion == "docx_to_pdf":
            from pypdf import PdfWriter

            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            writer.add_blank_page(width=72, height=144)
            writer.write(destination)
        else:
            from docx import Document

            document = Document()
            document.add_paragraph("Explicit UI worker double; not PDF text extraction evidence.")
            document.save(destination)
        connection.send({"stage": "validating"})
        path = Path(destination)
        connection.send(
            {
                "result": {
                    "size_bytes": path.stat().st_size,
                    "sha256": file_hash(path),
                    "warnings": ["Explicit UI worker double; not document engine validation."],
                    "preview": None,
                }
            }
        )
    finally:
        connection.close()
