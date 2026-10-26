"""Bounded, offline document conversion inside an already supervised worker.

Only executable discovery is used by HTTP capabilities. Document parsers are imported
inside conversion functions so the web process never parses an uploaded document.
"""

import math
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from contextlib import closing, contextmanager
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

from .archives import _guard_directory, canonical, safe_relative
from .errors import ConversionError
from .storage import file_hash

MiB = 1024**2
CHUNK = 64 * 1024
EXTERNAL_FIELDS = re.compile(r"\b(?:DDE(?:AUTO)?|INCLUDETEXT|INCLUDEPICTURE|LINK|DATABASE|RD)\b", re.I)


def libreoffice_executable(configured=None):
    """Discover a local installation without importing document/native parsers."""
    if configured:
        path = Path(configured).expanduser()
        if os.name == "nt" and path.name.lower() == "soffice.exe":
            console = path.with_suffix(".com")
            if console.is_file():
                return str(console.resolve())
        return str(path.resolve()) if path.is_file() else None
    commands = (
        ("soffice.com", "soffice", "libreoffice") if os.name == "nt" else ("soffice", "libreoffice")
    )
    for command in commands:
        if found := shutil.which(command):
            return found
    candidates = [Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")]
    if os.name == "nt":
        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)")):
            if base:
                candidates.extend(
                    Path(base) / "LibreOffice" / "program" / name
                    for name in ("soffice.com", "soffice.exe")
                )
    return next((str(path) for path in candidates if path.is_file()), None)


def _check_cancelled(cancelled):
    if cancelled():
        raise ConversionError("Document conversion cancelled.")


def _disk_check(path, reserve, extra=0):
    if shutil.disk_usage(path).free < reserve + extra:
        raise ConversionError("Not enough free disk space to finish this document.")


class _BoundedFile:
    def __init__(self, stream, path, maximum, reserve, cancelled):
        self.stream, self.path = stream, path
        self.maximum, self.reserve, self.cancelled = maximum, reserve, cancelled

    def write(self, data):
        _check_cancelled(self.cancelled)
        if self.stream.tell() + len(data) > self.maximum:
            raise ConversionError("Converted document exceeds the output size limit.")
        _disk_check(self.path.parent, self.reserve, len(data))
        return self.stream.write(data)

    def seek(self, *args):
        return self.stream.seek(*args)

    def tell(self):
        return self.stream.tell()

    def flush(self):
        return self.stream.flush()


def _xml_root(data):
    from lxml import etree

    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I):
        raise ConversionError("DOCX XML document types and entity declarations are unsupported.")
    parser = etree.XMLPullParser(
        events=("start",), resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False
    )
    nodes = 0
    try:
        for offset in range(0, len(data), CHUNK):
            parser.feed(data[offset : offset + CHUNK])
            for _event, _element in parser.read_events():
                nodes += 1
                if nodes > 200_000:
                    raise ConversionError("DOCX XML complexity exceeds the supported limit.")
        root = parser.close()
        if root.getroottree().docinfo.doctype:
            raise ConversionError("DOCX XML document types are unsupported.")
        return root
    except etree.XMLSyntaxError as exc:
        raise ConversionError("DOCX contains corrupt or unsupported XML.") from exc


def _relationship_target(name, target):
    split = urlsplit(target)
    if split.scheme or split.netloc or target.startswith("\\"):
        raise ConversionError(
            "DOCX external links and linked resources are unsupported for offline conversion."
        )
    target = unquote(split.path).replace("\\", "/")
    if not target:
        return None
    if target.startswith("/"):
        combined = posixpath.normpath(target.lstrip("/"))
    else:
        # word/_rels/document.xml.rels describes word/document.xml.
        owner = name.replace("/_rels/", "/").removesuffix(".rels")
        base = "" if name == "_rels/.rels" else posixpath.dirname(owner)
        combined = posixpath.normpath(posixpath.join(base, target))
    if combined == ".." or combined.startswith("../"):
        raise ConversionError("DOCX contains an unsafe internal relationship.")
    return safe_relative(combined)


def _content_types(archive, maximum, cancelled):
    """Identify XML by its OPC content type as well as its filename extension."""
    from lxml import etree

    entry = archive.getinfo("[Content_Types].xml")
    if entry.flag_bits & 1 or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise ConversionError(
            "DOCX content type declarations use unsupported compression or encryption."
        )
    if entry.file_size > maximum:
        raise ConversionError("DOCX XML part exceeds the supported size limit.")
    data = bytearray()
    with archive.open(entry) as source:
        while chunk := source.read(CHUNK):
            _check_cancelled(cancelled)
            data.extend(chunk)
            if len(data) > maximum:
                raise ConversionError("DOCX XML part exceeds the supported size limit.")
    root = _xml_root(bytes(data))
    if root.tag != "{http://schemas.openxmlformats.org/package/2006/content-types}Types":
        raise ConversionError("DOCX content type declarations are invalid.")
    overrides, defaults = {}, {}
    for element in root:
        content_type = element.get("ContentType", "").casefold()
        if content_type in {"image/svg+xml", "image/svg"}:
            raise ConversionError("DOCX SVG resources are unsupported for offline conversion.")
        if any(
            token in content_type for token in ("macroenabled", "vbaproject", "activex", "oleobject")
        ):
            raise ConversionError("DOCX active or macro-enabled content is unsupported.")
        local = etree.QName(element).localname
        if local == "Override":
            name = canonical(safe_relative(unquote(element.get("PartName", "").lstrip("/"))))
            overrides[name] = content_type
        elif local == "Default":
            defaults[element.get("Extension", "").casefold()] = content_type
    main_type = overrides.get("word/document.xml", defaults.get("xml"))
    if main_type != "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml":
        raise ConversionError("File is not a supported DOCX document.")
    xml_parts = {name for name, value in overrides.items() if value.endswith(("/xml", "+xml"))}
    xml_extensions = {name for name, value in defaults.items() if value.endswith(("/xml", "+xml"))}
    return xml_parts, xml_extensions


def _validate_docx(path, limits, cancelled, *, generated=False):
    """Inspect ZIP/XML in bounded chunks; never extract archive-selected host paths."""
    from lxml import etree

    expanded_limit = limits["document_expanded_max_bytes"]
    xml_limit = min(expanded_limit, 16 * MiB)
    zip_limits = SimpleNamespace(
        zip_max_entries=min(limits.get("zip_max_entries", 10_000), 5_000),
        zip_directory_max_bytes=min(limits.get("zip_directory_max_bytes", 32 * MiB), 8 * MiB),
    )
    try:
        _guard_directory(path, zip_limits)
        with zipfile.ZipFile(path) as archive:
            xml_parts, xml_extensions = _content_types(archive, xml_limit, cancelled)
            entries = archive.infolist()
            names = {}
            expanded = 0
            relationships = []
            main_relationship = main_document = False
            for entry in entries:
                _check_cancelled(cancelled)
                name = safe_relative(entry.orig_filename)
                normalized = canonical(name)
                if normalized in names:
                    raise ConversionError("DOCX contains duplicate or ambiguous package entries.")
                names[normalized] = name
                kind = stat.S_IFMT((entry.external_attr >> 16) & 0xFFFF)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or entry.flag_bits & 1:
                    raise ConversionError(
                        "DOCX links, special files and encrypted entries are unsupported."
                    )
                if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    raise ConversionError("DOCX compression method is unsupported.")
                if entry.is_dir():
                    continue
                if (
                    "vbaproject" in normalized
                    or "/activex/" in normalized
                    or "/embeddings/" in normalized
                    or normalized.endswith((".svg", ".svgz"))
                ):
                    raise ConversionError(
                        "DOCX macros, active content, embedded objects and SVG resources are unsupported."
                    )
                if not generated and entry.file_size > max(
                    1000, limits.get("compression_ratio", 200)
                ) * max(1, entry.compress_size):
                    raise ConversionError("DOCX entry exceeds the compression ratio limit.")
                expanded += entry.file_size
                if expanded > expanded_limit:
                    raise ConversionError("DOCX expanded content exceeds the configured limit.")
                is_xml = (
                    normalized.endswith((".xml", ".rels"))
                    or normalized in xml_parts
                    or normalized.rsplit(".", 1)[-1] in xml_extensions
                )
                if is_xml and entry.file_size > xml_limit:
                    raise ConversionError("DOCX XML part exceeds the supported size limit.")
                data = bytearray() if is_xml else None
                count = 0
                with archive.open(entry) as source:
                    while chunk := source.read(CHUNK):
                        _check_cancelled(cancelled)
                        count += len(chunk)
                        if count > entry.file_size or count > expanded_limit:
                            raise ConversionError("DOCX expanded content exceeds its declared bounds.")
                        if data is None and count == len(chunk):
                            prefix = chunk.lstrip(b" \t\r\n")
                            if prefix.startswith(b"\xef\xbb\xbf"):
                                prefix = prefix[3:].lstrip(b" \t\r\n")
                            if prefix.startswith(
                                (b"<", b"\xff\xfe", b"\xfe\xff", b"\x00<", b"\x00\x00\x00<")
                            ):
                                data = bytearray()
                        if data is not None:
                            if count > xml_limit or entry.file_size > xml_limit:
                                raise ConversionError("DOCX XML part exceeds the supported size limit.")
                            data.extend(chunk)
                if count != entry.file_size:
                    raise ConversionError("DOCX package member size does not match.")
                if data is None:
                    continue
                root = _xml_root(bytes(data))
                if normalized == "word/document.xml":
                    main_document = root.tag in {
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}document",
                        "{http://purl.oclc.org/ooxml/wordprocessingml/main}document",
                    }
                if normalized == "[content_types].xml":
                    values = " ".join(root.xpath("//@ContentType")).casefold()
                    if any(
                        token in values
                        for token in ("macroenabled", "vbaproject", "activex", "oleobject")
                    ):
                        raise ConversionError("DOCX active or macro-enabled content is unsupported.")
                fields = []
                for element in root.iter():
                    if not isinstance(element.tag, str):
                        continue
                    qualified = etree.QName(element)
                    if qualified.namespace == "http://www.w3.org/2000/svg":
                        raise ConversionError(
                            "DOCX SVG resources are unsupported for offline conversion."
                        )
                    local = qualified.localname
                    if local == "Relationship":
                        relationship_type = element.get("Type", "").casefold()
                        if any(
                            token in relationship_type
                            for token in (
                                "vbaproject",
                                "activex",
                                "oleobject",
                                "afchunk",
                                "attachedtemplate",
                            )
                        ) or relationship_type.endswith("/package"):
                            raise ConversionError(
                                "DOCX active content and embedded objects are unsupported."
                            )
                        if element.get("TargetMode", "").strip().casefold() == "external":
                            raise ConversionError(
                                "DOCX external links and linked resources are unsupported for offline conversion."
                            )
                        if target := _relationship_target(name, element.get("Target", "")):
                            relationships.append(target)
                            if (
                                normalized == "_rels/.rels"
                                and relationship_type.endswith("/officedocument")
                                and canonical(target) == "word/document.xml"
                            ):
                                main_relationship = True
                    if local in {
                        "altChunk",
                        "object",
                        "OLEObject",
                        "control",
                        "attachedTemplate",
                        "subDoc",
                        "mailMerge",
                    }:
                        raise ConversionError(
                            "DOCX active content and externally linked documents are unsupported."
                        )
                    if local == "instrText":
                        fields.append("".join(element.itertext()))
                    for key, value in element.attrib.items():
                        if etree.QName(key).localname == "instr":
                            fields.append(value)
                if EXTERNAL_FIELDS.search("".join(fields)):
                    raise ConversionError(
                        "DOCX external data fields are unsupported for offline conversion."
                    )
            if not {"[content_types].xml", "_rels/.rels", "word/document.xml"} <= names.keys():
                raise ConversionError("File is not a supported DOCX document.")
            if not main_document or not main_relationship:
                raise ConversionError("DOCX main document structure is invalid or unsupported.")
            if any(canonical(target) not in names for target in relationships):
                raise ConversionError("DOCX contains a missing or invalid internal relationship.")
    except ConversionError:
        raise
    except (OSError, ValueError, KeyError, RuntimeError, NotImplementedError, zipfile.BadZipFile) as exc:
        raise ConversionError("DOCX is corrupt or not a supported Word document.") from exc


def _pdf_configuration(limits):
    from pypdf import apply_configuration

    maximum = limits["pdf_page_content_max_bytes"]
    return apply_configuration(
        maximum_declared_stream_length=maximum,
        array_based_stream_maximum_output_length=maximum,
        zlib_maximum_output_length=maximum,
        lzw_maximum_output_length=maximum,
        run_length_maximum_output_length=maximum,
        brotli_maximum_output_length=maximum,
        jbig2_maximum_output_length=maximum,
        image_maximum_buffer_size=maximum,
        stream_decoding_work_maximum_length=maximum * 4,
        stream_parsing_work_maximum_count=200_000,
        page_tree_maximum_entries=limits["document_max_pages"] * 4 + 100,
        page_tree_maximum_depth=32,
        array_maximum_element_count=20_000,
        dictionary_maximum_element_count=20_000,
        xform_maximum_invocations_per_extraction=1_000,
        jbig2dec_binary=None,
    )


def _page_count(reader, limits):
    if reader.is_encrypted:
        raise ConversionError(
            "Encrypted or password-protected PDFs are unsupported. Save an unencrypted copy first."
        )
    count = len(reader.pages)
    if not 0 < count <= limits["document_max_pages"]:
        raise ConversionError("PDF page count exceeds the configured limit or the PDF has no pages.")
    for page in reader.pages:
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        if not all(math.isfinite(value) and 0 < value <= 200_000 for value in (width, height)):
            raise ConversionError("PDF page dimensions are invalid or unsupported.")
    return count


@contextmanager
def _open_pdf(path, limits):
    from pypdf import PdfReader
    from pypdf.errors import DependencyError, FileNotDecryptedError, LimitReachedError, PyPdfError

    try:
        with (
            _pdf_configuration(limits),
            path.open("rb") as stream,
            closing(PdfReader(stream, strict=True)) as reader,
        ):
            if reader.is_encrypted:
                raise ConversionError(
                    "Encrypted or password-protected PDFs are unsupported. Save an unencrypted copy first."
                )
            yield reader
    except LimitReachedError as exc:
        raise ConversionError(
            "PDF decoding or structural complexity exceeds the configured limit."
        ) from exc
    except (FileNotDecryptedError, DependencyError) as exc:
        raise ConversionError(
            "Encrypted or password-protected PDFs are unsupported. Save an unencrypted copy first."
        ) from exc
    except PyPdfError as exc:
        raise ConversionError(
            "PDF is corrupt or unsupported by the local text extraction engine."
        ) from exc


def _validate_pdf(path, limits):
    with _open_pdf(path, limits) as reader:
        return _page_count(reader, limits)


def _pdf_to_docx(source, output, limits, progress, cancelled):
    from docx import Document

    document = Document()
    count = characters = nonempty = paragraphs = 0
    empty = []
    with _open_pdf(source, limits) as reader:
        count = _page_count(reader, limits)
        for index, page in enumerate(reader.pages):
            _check_cancelled(cancelled)
            contents = page.get_contents()
            if contents is not None and len(contents.get_data()) > limits["pdf_page_content_max_bytes"]:
                raise ConversionError("PDF page content exceeds the configured decoding limit.")
            text = page.extract_text() or ""
            characters += len(text)
            if characters > limits["document_max_characters"]:
                raise ConversionError("PDF extracted text exceeds the configured character limit.")
            # OOXML cannot represent most C0 controls or unpaired surrogate characters.
            text = "".join(
                char
                for char in text
                if char in "\t\n\r"
                or 32 <= ord(char) <= 0xD7FF
                or 0xE000 <= ord(char) <= 0xFFFD
                or 0x10000 <= ord(char) <= 0x10FFFF
            )
            if index:
                document.add_page_break()
            if text.strip():
                nonempty += 1
                for paragraph in text.splitlines():
                    paragraphs += 1
                    if paragraphs > 100_000:
                        raise ConversionError(
                            "PDF text structure exceeds the supported paragraph limit."
                        )
                    document.add_paragraph(paragraph)
            else:
                empty.append(index + 1)
    if not nonempty:
        raise ConversionError(
            "PDF contains no extractable text. Scanned or image-only PDFs need OCR, which is not included."
        )
    progress("encoding")
    _save_docx(document, output, limits, cancelled)
    warnings = [
        "PDF to DOCX extracts editable text and page breaks. Original fonts, images, tables and page layout are not reconstructed; no OCR is included."
    ]
    if empty:
        warnings.append(
            f"{len(empty)} page(s) had no extractable text and were retained as blank page breaks."
        )
    return count, warnings


def _save_docx(document, output, limits, cancelled):
    # python-docx 1.2's PackageWriter.write omits finally around its ZIP writer.
    # Own that writer so cancellation/quota/disk errors close it before our file
    # handle closes. Reuse its existing OPC serializer unchanged.
    from docx.opc.phys_pkg import PhysPkgWriter
    from docx.opc.pkgwriter import PackageWriter

    package = document.part.package
    parts = package.parts
    for part in parts:
        part.before_marshal()
    with output.open("xb") as stream:
        checked = _BoundedFile(
            stream, output, limits["document_output_max_bytes"], limits["min_free_bytes"], cancelled
        )
        with closing(PhysPkgWriter(checked)) as writer:
            PackageWriter._write_content_types_stream(writer, parts)
            PackageWriter._write_pkg_rels(writer, package.rels)
            PackageWriter._write_parts(writer, parts)
        stream.flush()
        os.fsync(stream.fileno())


def _profile(profile):
    user = profile / "user"
    user.mkdir(parents=True)
    (user / "registrymodifications.xcu").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
        '<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>'
        '<prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>'
        '</item><item oor:path="/org.openoffice.Office.Writer/Content/Update">'
        '<prop oor:name="Link" oor:op="fuse"><value>2</value></prop>'
        '<prop oor:name="Field" oor:op="fuse"><value>false</value></prop>'
        '<prop oor:name="Chart" oor:op="fuse"><value>false</value></prop>'
        '</item><item oor:path="/org.openoffice.Office.Common/Misc">'
        '<prop oor:name="FirstRun" oor:op="fuse"><value>false</value></prop>'
        '</item><item oor:path="/org.openoffice.Setup/Office">'
        '<prop oor:name="ooSetupInstCompleted" oor:op="fuse"><value>true</value></prop>'
        '</item><item oor:path="/org.openoffice.Office.Jobs/Jobs/org.openoffice.Office.Jobs:Job[&apos;UpdateCheck&apos;]/Arguments">'
        '<prop oor:name="AutoCheckEnabled" oor:type="xs:boolean" oor:op="fuse"><value>false</value></prop>'
        '<prop oor:name="AutoDownloadEnabled" oor:type="xs:boolean" oor:op="fuse"><value>false</value></prop>'
        "</item></oor:items>",
        encoding="utf-8",
    )


@contextmanager
def _external_dll_directory():
    # Frozen Windows children inherit PyInstaller's DLL search directory. LibreOffice
    # must load its own DLLs instead; this reset is confined to the isolated worker.
    if os.name != "nt" or not getattr(sys, "frozen", False):
        yield
        return
    import ctypes

    kernel = ctypes.windll.kernel32
    length = kernel.GetDllDirectoryW(0, None)
    buffer = ctypes.create_unicode_buffer(length + 1)
    kernel.GetDllDirectoryW(len(buffer), buffer)
    previous = buffer.value
    if not kernel.SetDllDirectoryW(None):
        raise ConversionError("Could not prepare the local document engine.")
    try:
        yield
    finally:
        kernel.SetDllDirectoryW(previous or None)


def _stop_process_tree(process):
    import psutil

    try:
        parent = psutil.Process(process.pid)
        for child in reversed(parent.children(recursive=True)):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


def _office_cli_path(path):
    """Use an existing Windows 8.3 alias for the same file; never relocate data."""
    path = Path(path)
    if os.name != "nt":
        return path
    import ctypes

    get_short = ctypes.windll.kernel32.GetShortPathNameW
    get_short.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32]
    get_short.restype = ctypes.c_uint32
    required = get_short(str(path), None, 0)
    if not required:
        return path
    buffer = ctypes.create_unicode_buffer(required)
    if not get_short(str(path), buffer, required):
        return path
    shortened = Path(buffer.value)
    try:
        return shortened if len(str(shortened)) < len(str(path)) and path.samefile(shortened) else path
    except OSError:
        return path


def _office_profile_path(profile):
    shortened = _office_cli_path(profile)
    # LibreOffice 26.8's extension bootstrap can silently stop with exit 0 when
    # these native profile paths exceed MAX_PATH. Never move the workspace.
    cache = (
        shortened
        / "user/uno_packages/cache/registry/com.sun.star.comp.deployment.configuration.PackageRegistryBackend/backenddb.xml"
    )
    if os.name == "nt" and len(str(cache)) >= 260:
        raise ConversionError(
            "LibreOffice needs a shorter workspace path on this Windows system. Use a shorter --workspace location or enable Windows 8.3 file names, then retry."
        )
    return shortened


def _docx_to_pdf(source, scratch, limits, progress, cancelled):
    executable = libreoffice_executable(limits.get("libreoffice"))
    if not executable:
        raise ConversionError(
            "DOCX to PDF needs LibreOffice installed locally. Set its soffice executable in the libreoffice setting, then restart CapreConvert."
        )
    _validate_docx(source, limits, cancelled)
    staged = scratch / "input.docx"
    with source.open("rb") as original, staged.open("xb") as output:
        while chunk := original.read(CHUNK):
            _check_cancelled(cancelled)
            _disk_check(scratch, limits["min_free_bytes"], len(chunk))
            output.write(chunk)
    profile = scratch / "profile"
    _profile(profile)
    output_dir = scratch / "output"
    output_dir.mkdir()
    output = output_dir / "input.pdf"
    progress("encoding")
    environment = dict(os.environ)
    for variable in ("PYTHONHOME", "PYTHONPATH"):
        environment.pop(variable, None)
    if "LD_LIBRARY_PATH_ORIG" in environment:
        environment["LD_LIBRARY_PATH"] = environment["LD_LIBRARY_PATH_ORIG"]
    elif getattr(sys, "frozen", False):
        environment.pop("LD_LIBRARY_PATH", None)
    environment["SAL_DISABLE_OPENCL"] = "1"
    cli_profile = _office_profile_path(profile)
    with _external_dll_directory():
        process = subprocess.Popen(
            [
                str(_office_cli_path(executable)),
                f"-env:UserInstallation={cli_profile.as_uri()}",
                "--headless",
                "--nologo",
                "--nodefault",
                "--norestore",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(_office_cli_path(output_dir)),
                str(_office_cli_path(staged)),
            ],
            cwd=_office_cli_path(scratch),
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    started = time.monotonic()
    try:
        while process.poll() is None:
            _check_cancelled(cancelled)
            if time.monotonic() - started > limits["file_timeout_seconds"]:
                raise ConversionError("DOCX to PDF conversion timed out.")
            if output.is_file() and output.stat().st_size > limits["document_output_max_bytes"]:
                raise ConversionError("Converted PDF exceeds the output size limit.")
            _disk_check(scratch, limits["min_free_bytes"])
            time.sleep(0.1)
        if process.returncode or not output.is_file():
            raise ConversionError(
                "LibreOffice could not convert this DOCX. Check it opens locally and is not password-protected."
            )
    finally:
        _stop_process_tree(process)
    return output


def convert_document(
    source,
    destination,
    settings,
    limits,
    progress=lambda stage: None,
    admit=lambda memory: None,
    cancelled=lambda: False,
):
    """Convert in an isolated worker and publish only a fully validated document."""
    source, destination = Path(source), Path(destination)
    parent = destination.parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(limits["scratch_dir"]).resolve()
    if scratch.parent != parent or not scratch.name.startswith("document-"):
        raise ConversionError("Document worker staging location is invalid.")
    if source.resolve() == destination.resolve() or destination.exists():
        raise ConversionError("Document output already exists or would replace its input.")
    if not 0 < source.stat().st_size <= limits["document_max_bytes"]:
        raise ConversionError("Document input exceeds the configured size limit or is empty.")
    _check_cancelled(cancelled)
    _disk_check(parent, limits["min_free_bytes"])
    admit(limits["document_memory_bytes"])
    scratch.mkdir(mode=0o700, exist_ok=False)
    try:
        progress("decoding")
        if settings.conversion == "pdf_to_docx":
            output = scratch / "generated.docx"
            pages, warnings = _pdf_to_docx(source, output, limits, progress, cancelled)
            progress("validating")
            _validate_docx(output, limits, cancelled, generated=True)
        elif settings.conversion == "docx_to_pdf":
            output = _docx_to_pdf(source, scratch, limits, progress, cancelled)
            progress("validating")
            pages = _validate_pdf(output, limits)
            warnings = [
                "DOCX to PDF uses local LibreOffice. Fonts missing on this computer may change document layout."
            ]
        else:
            raise ConversionError("Unsupported document conversion type.")
        if not 0 < output.stat().st_size <= limits["document_output_max_bytes"]:
            raise ConversionError("Converted document is empty or exceeds the output size limit.")
        _check_cancelled(cancelled)
        _disk_check(parent, limits["min_free_bytes"])
        metadata = {
            "pages": pages,
            "warnings": warnings,
            "size_bytes": output.stat().st_size,
            "sha256": file_hash(output),
            "preview": None,
        }
        if destination.exists():
            raise ConversionError("Document output already exists.")
        os.replace(output, destination)
        return metadata
    except ConversionError:
        raise
    except (MemoryError, RecursionError) as exc:
        raise ConversionError(
            "Document complexity exceeds this worker's supported resource limits."
        ) from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ConversionError("Document is corrupt or cannot be converted by the local engine.") from exc
    finally:
        checked = scratch.resolve()
        if checked.parent != parent or not checked.name.startswith("document-"):
            raise RuntimeError("Refusing to remove an unverified document staging directory.")
        shutil.rmtree(checked)
