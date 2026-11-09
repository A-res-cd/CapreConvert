"""ODF package guards and real local LibreOffice round trips."""

import hashlib
import os
import zipfile

import pytest
from docx import Document
from pypdf import PdfReader

from localraw import documents
from localraw.errors import ConversionError
from tests.unit import test_documents
from tests.unit.test_documents import convert, text_pdf


@pytest.fixture
def limits(tmp_path):
    return test_documents.limits.__wrapped__(tmp_path)


def odt(path, body="<text:p>Editable ODF text</text:p>", extras=()):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archive.writestr(
            "content.xml",
            (
                '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
                'xmlns:xlink="http://www.w3.org/1999/xlink">'
                "<office:body><office:text>"
                + body
                + "</office:text></office:body></office:document-content>"
            ),
        )
        archive.writestr(
            "META-INF/manifest.xml",
            (
                '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
                '<manifest:file-entry manifest:full-path="/" '
                'manifest:media-type="application/vnd.oasis.opendocument.text"/>'
                '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>'
                "</manifest:manifest>"
            ),
        )
        for name, content in extras:
            archive.writestr(name, content)
    return path


@pytest.mark.parametrize(
    "body,extras",
    [
        ('<text:a xlink:href="https://example.com">external</text:a>', ()),
        ('<text:a xlink:href="file:///C:/secret.txt">file</text:a>', ()),
        ('<text:p xlink:href="../secret">escape</text:p>', ()),
        ("<office:script/>", ()),
        ("<office:object/>", ()),
        ("<text:p>text</text:p>", (("../escape.xml", "<root/>"),)),
        ("<text:p>text</text:p>", (("Basic/code.bin", b"active"),)),
        ("<text:p>text</text:p>", (("META-INF/encryption.xml", "<encryption-data/>"),)),
        (
            "<text:p>text</text:p>",
            (("secret.xml", '<!DOCTYPE x [<!ENTITY e SYSTEM "file:///secret">]><x>&e;</x>'),),
        ),
        (
            "<text:p>text</text:p>",
            (
                (
                    "Pictures/hidden.png",
                    '<office:script xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"/>',
                ),
            ),
        ),
    ],
)
def test_unsafe_odt_never_reaches_native_engine(tmp_path, limits, monkeypatch, body, extras):
    source = odt(tmp_path / "source.odt", body, extras)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    monkeypatch.setattr(documents, "libreoffice_executable", lambda configured=None: "unused")
    monkeypatch.setattr(
        documents.subprocess, "Popen", lambda *a, **kw: pytest.fail("unsafe native launch")
    )
    with pytest.raises(ConversionError):
        convert(source, tmp_path / "out.pdf", limits, "odt_to_pdf")
    assert not (tmp_path / "out.pdf").exists()
    assert not limits["scratch_dir"].exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_odt_expanded_and_xml_limits(tmp_path, limits):
    source = odt(tmp_path / "input.odt")
    documents._validate_odt(source, limits, lambda: False)
    limits["document_expanded_max_bytes"] = 20
    with pytest.raises(ConversionError, match="limit"):
        documents._validate_odt(source, limits, lambda: False)


@pytest.mark.parametrize(
    "change",
    ["wrong_mime", "missing_body", "missing_manifest", "encrypted", "duplicate", "symlink", "corrupt"],
)
def test_invalid_odt_package_rejected_before_native(tmp_path, limits, monkeypatch, change):
    source = odt(tmp_path / "source.odt")
    with zipfile.ZipFile(source) as archive:
        members = [(entry.filename, archive.read(entry)) for entry in archive.infolist()]
    if change == "corrupt":
        source.write_bytes(b"not a document")
    else:
        with zipfile.ZipFile(source, "w") as archive:
            for name, data in members:
                if change == "wrong_mime" and name == "mimetype":
                    data = b"application/vnd.oasis.opendocument.spreadsheet"
                if change == "missing_body" and name == "content.xml":
                    data = b"<root/>"
                if change == "missing_manifest" and name == "META-INF/manifest.xml":
                    continue
                if change == "encrypted" and name == "META-INF/manifest.xml":
                    data = data.replace(
                        b"</manifest:manifest>", b"<manifest:encryption-data/></manifest:manifest>"
                    )
                archive.writestr(name, data)
            if change == "duplicate":
                archive.writestr("CONTENT.xml", b"<root/>")
            if change == "symlink":
                entry = zipfile.ZipInfo("link.xml")
                entry.create_system = 3
                entry.external_attr = 0o120777 << 16
                archive.writestr(entry, "outside")
    monkeypatch.setattr(documents, "libreoffice_executable", lambda configured=None: "unused")
    monkeypatch.setattr(
        documents.subprocess, "Popen", lambda *a, **kw: pytest.fail("invalid native launch")
    )
    with pytest.raises(ConversionError):
        convert(source, tmp_path / "out.docx", limits, "odt_to_docx")
    assert not (tmp_path / "out.docx").exists()
    assert not limits["scratch_dir"].exists()


@pytest.mark.skipif(
    not os.environ.get("LOCALRAW_TEST_LIBREOFFICE"), reason="External LibreOffice required"
)
def test_real_native_odt_docx_pdf_and_pdf_odt(tmp_path, limits):
    limits["libreoffice"] = os.environ["LOCALRAW_TEST_LIBREOFFICE"]
    limits["file_timeout_seconds"] = 120
    source = tmp_path / "original.docx"
    document = Document()
    document.add_heading("ODF native round trip", 1)
    document.add_paragraph("Editable ODF text")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "First cell"
    table.cell(0, 1).text = "Second cell"
    document.save(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    odt_file = tmp_path / "converted.odt"
    convert(source, odt_file, limits, "docx_to_odt")
    documents._validate_odt(odt_file, limits, lambda: False, generated=True)
    odt_hash = hashlib.sha256(odt_file.read_bytes()).hexdigest()
    target = tmp_path / "returned.docx"
    convert(odt_file, target, limits, "odt_to_docx")
    returned = Document(target)
    assert "Editable ODF text" in [p.text for p in returned.paragraphs]
    assert returned.tables[0].cell(0, 1).text == "Second cell"
    target = tmp_path / "rendered.pdf"
    convert(odt_file, target, limits, "odt_to_pdf")
    with target.open("rb") as stream:
        reader = PdfReader(stream)
        assert "Editable ODF text" in reader.pages[0].extract_text()
        reader.close()
    pdf = text_pdf(tmp_path / "source.pdf", ("First selectable page", "Second selectable page"))
    result = convert(pdf, tmp_path / "extracted.odt", limits, "pdf_to_odt")
    with zipfile.ZipFile(tmp_path / "extracted.odt") as archive:
        content = archive.read("content.xml")
        assert b"First selectable page" in content and b"Second selectable page" in content
    assert result["pages"] == 2 and any("no OCR" in warning for warning in result["warnings"])
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert hashlib.sha256(odt_file.read_bytes()).hexdigest() == odt_hash
    assert not limits["scratch_dir"].exists()


def test_odt_preview_is_bounded_plain_content(tmp_path):
    import json

    from localraw.config import Settings
    from localraw.previews import render_worker

    class Connection:
        def send(self, result):
            self.result = result

        def close(self):
            pass

    source = odt(tmp_path / "source.odt", "<text:p>&lt;script&gt;plain text&lt;/script&gt;</text:p>")
    target = tmp_path / "preview.json"
    connection = Connection()
    settings = Settings(workspace=tmp_path, min_free_bytes=0, preview_text_characters=12)
    render_worker(str(source), str(target), "odt", 1, settings.model_dump(mode="json"), connection)
    assert "error" not in connection.result, connection.result
    result = json.loads(target.read_text())
    assert result["kind"] == "odt" and result["truncated"]
    assert result["blocks"] == [{"type": "paragraph", "text": "<script>plai"}]
