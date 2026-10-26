"""Strict ZIP inspection, generated staging paths and deterministic output names."""

import os
import re
import stat
import struct
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from .errors import Problem

DEVICE = re.compile(
    r"^(CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|CLOCK\$|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.IGNORECASE
)


def safe_relative(name: str) -> str:
    if "\x00" in name or not name or len(name) > 1024:
        raise ValueError("Unsafe archive or input filename.")
    name = unicodedata.normalize("NFC", name.replace("\\", "/"))
    if name.startswith("/"):
        raise ValueError("Absolute archive paths are forbidden.")
    components = name.rstrip("/").split("/")
    for component in components:
        if (
            not component
            or component in (".", "..")
            or len(component) > 240
            or component.rstrip(" .") != component
            or DEVICE.match(component.split(".", 1)[0].rstrip(" ."))
            or any(ord(char) < 32 or char in '<>:"|?*' for char in component)
        ):
            raise ValueError("Unsafe archive or input filename.")
    return "/".join(components)


def safe_filename(name):
    normalized = safe_relative(name)
    if "/" in normalized:
        raise ValueError("A filename must not contain directories.")
    return normalized


def canonical(name):
    return unicodedata.normalize("NFC", name).casefold()


class OutputNames:
    def __init__(self):
        self.files = set()
        self.directories = {canonical("files")}
        self.archive_roots = {canonical("files")}

    def archive_root(self, filename):
        stem = PurePosixPath(safe_filename(filename)).stem
        candidate, number = stem, 1
        while canonical(candidate) in self.archive_roots:
            number += 1
            candidate = f"{stem}__{number}"
        self.archive_roots.add(canonical(candidate))
        self.directories.add(canonical(candidate))
        return candidate

    def jpeg(self, relative, suffix=""):
        return self.output(relative, suffix, ".jpg")

    def output(self, relative, suffix="", extension=".jpg"):
        from .formats import CONVERSIONS

        if extension not in {entry.output_extension for entry in CONVERSIONS.values()}:
            raise ValueError("Unsupported output extension.")
        path = PurePosixPath(safe_relative(relative))
        parts = []
        for component in path.parts[:-1]:
            base, candidate, number = component, component, 1
            while canonical("/".join([*parts, candidate])) in self.files:
                number += 1
                candidate = f"{base}__{number}"
            parts.append(candidate)
            self.directories.add(canonical("/".join(parts)))
        stem = path.stem[: max(1, 228 - len(suffix))] + suffix
        candidate, number = "/".join([*parts, stem + extension]), 1
        while canonical(candidate) in self.files | self.directories:
            number += 1
            candidate = "/".join([*parts, f"{stem}__{number}{extension}"])
        self.files.add(canonical(candidate))
        return candidate


def _guard_directory(path, limits):
    """Bound central-directory work before ZipFile allocates its in-memory entry list."""
    size = path.stat().st_size
    with path.open("rb") as stream:
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
        end = tail.rfind(b"PK\x05\x06")
        if end < 0 or len(tail) - end < 22:
            raise ValueError("ZIP end record is missing.")
        _, disk, directory_disk, disk_count, count, directory_size, offset, comment = struct.unpack_from(
            "<4s4H2IH", tail, end
        )
        if disk or directory_disk or disk_count != count or end + 22 + comment != len(tail):
            raise ValueError("Invalid or multi-disk ZIP archive.")
        if count == 65535 or directory_size == 0xFFFFFFFF or offset == 0xFFFFFFFF:
            absolute_end = size - len(tail) + end
            stream.seek(max(0, absolute_end - 20))
            locator = stream.read(20)
            if len(locator) != 20 or locator[:4] != b"PK\x06\x07":
                raise ValueError("ZIP64 locator is invalid.")
            _, zip_disk, position, disks = struct.unpack("<4sIQI", locator)
            if zip_disk or disks != 1 or position + 56 > size:
                raise ValueError("ZIP64 disk information is invalid.")
            stream.seek(position)
            record = stream.read(56)
            if len(record) != 56 or record[:4] != b"PK\x06\x06":
                raise ValueError("ZIP64 directory is invalid.")
            _, _, _, _, disk, directory_disk, disk_count, count, directory_size, offset = struct.unpack(
                "<4sQ2H2I4Q", record
            )
            if disk or directory_disk or disk_count != count:
                raise ValueError("Multi-disk ZIP64 archives are unsupported.")
        if count > limits.zip_max_entries or directory_size > limits.zip_directory_max_bytes:
            raise ValueError("ZIP central directory exceeds the configured entry or byte limit.")
        if offset + directory_size > size:
            raise ValueError("ZIP central directory is out of bounds.")
        stream.seek(offset)
        actual = 0
        while stream.tell() < offset + directory_size:
            fixed = stream.read(46)
            if len(fixed) != 46 or fixed[:4] != b"PK\x01\x02":
                raise ValueError("ZIP central directory entry is invalid.")
            name_size, extra_size, comment_size = struct.unpack_from("<3H", fixed, 28)
            stream.seek(name_size + extra_size + comment_size, 1)
            actual += 1
            if actual > limits.zip_max_entries or stream.tell() > offset + directory_size:
                raise ValueError("ZIP central directory exceeds its declared bounds.")
        if actual != count:
            raise ValueError("ZIP central directory entry count does not match.")


def _guard_lzma(path, entry, limits):
    # ZIP's raw LZMA decoder does not accept a memory limit. Inspect its dictionary
    # property before constructing that decoder, even when expanded bytes are small.
    with path.open("rb") as source:
        source.seek(entry.header_offset)
        header = source.read(30)
        if len(header) != 30 or header[:4] != b"PK\x03\x04":
            raise ValueError("ZIP LZMA local header is invalid.")
        name_size, extra_size = struct.unpack_from("<HH", header, 26)
        source.seek(name_size + extra_size, 1)
        properties = source.read(9)
        if len(properties) != 9 or struct.unpack_from("<H", properties, 2)[0] != 5:
            raise ValueError("ZIP LZMA properties are unsupported.")
        dictionary = struct.unpack_from("<I", properties, 5)[0]
        if dictionary > limits.zip_lzma_dictionary_max_bytes:
            raise ValueError("ZIP LZMA dictionary exceeds the memory guard.")


def inspect_archive(path: Path, limits):
    """Validate every entry before selecting any. Caller continues independent inputs."""
    selected, skipped = [], []
    expanded = compressed = 0
    try:
        _guard_directory(path, limits)
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > limits.zip_max_entries:
                raise ValueError("ZIP contains too many entries.")
            for index, entry in enumerate(entries):
                name = safe_relative(entry.orig_filename)
                mode = (entry.external_attr >> 16) & 0xFFFF
                kind = stat.S_IFMT(mode)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError("ZIP links and special files are forbidden.")
                if entry.flag_bits & 1:
                    raise ValueError("Encrypted ZIP entries are unsupported.")
                if entry.compress_type not in (
                    zipfile.ZIP_STORED,
                    zipfile.ZIP_DEFLATED,
                    zipfile.ZIP_BZIP2,
                    zipfile.ZIP_LZMA,
                ):
                    raise ValueError("ZIP compression method is unsupported.")
                expanded += entry.file_size
                compressed += entry.compress_size
                if entry.file_size > limits.compression_ratio * max(1, entry.compress_size):
                    raise ValueError("ZIP entry exceeds the compression ratio limit.")
                if expanded > limits.expanded_max_bytes:
                    raise ValueError("ZIP expanded size exceeds the job limit.")
                if entry.is_dir():
                    continue
                if kind == stat.S_IFDIR:
                    raise ValueError("Invalid ZIP directory entry.")
                if PurePosixPath(name).suffix.lower() == ".cr3":
                    if entry.compress_type == zipfile.ZIP_LZMA:
                        _guard_lzma(path, entry, limits)
                    if entry.file_size > limits.raw_max_bytes or entry.file_size == 0:
                        raise ValueError("Archived RAW size exceeds the allowed range.")
                    selected.append({"index": index, "relative": name, "size_bytes": entry.file_size})
                else:
                    skipped.append(name)
            if expanded > limits.compression_ratio * max(1, compressed):
                raise ValueError("ZIP exceeds the aggregate compression ratio limit.")
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, OSError) as exc:
        raise ValueError("ZIP is corrupt or unreadable.") from exc
    return selected, skipped, expanded


def extract_selected(
    archive_path: Path,
    selected,
    target: Path,
    limits,
    write_check=lambda n: None,
    cancelled=lambda: False,
):
    """Never use archive names as host paths; stream one selected entry to a generated target."""
    part = target.with_suffix(".cr3.part")
    count = 0
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entry = archive.infolist()[selected["index"]]
            with archive.open(entry) as source, part.open("wb") as output:
                while chunk := source.read(1024**2):
                    if cancelled():
                        raise ValueError("Extraction cancelled.")
                    count += len(chunk)
                    if count > limits.raw_max_bytes or count > selected["size_bytes"]:
                        raise ValueError("Extracted RAW exceeds its declared size or limit.")
                    output.write(chunk)
                    write_check(len(chunk))
                output.flush()
                os.fsync(output.fileno())
            if count != selected["size_bytes"]:
                raise ValueError("Incomplete ZIP entry.")
        os.replace(part, target)
        return count
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError) as exc:
        raise ValueError("ZIP entry is corrupt or failed its CRC check.") from exc
    finally:
        part.unlink(missing_ok=True)


def package_outputs(destination: Path, outputs, write_check=lambda n: None, cancelled=lambda: False):
    """Only caller-committed successful JPEGs; report is a separate endpoint."""
    partial = destination.with_suffix(".zip.part")
    try:
        with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for item in outputs:
                name = safe_relative(item["output_name"])
                with (
                    Path(item["path"]).open("rb") as source,
                    archive.open(name, "w", force_zip64=True) as out,
                ):
                    while chunk := source.read(1024**2):
                        if cancelled():
                            raise ValueError("Packaging interrupted.")
                        out.write(chunk)
                        write_check(len(chunk))
        with zipfile.ZipFile(partial) as archive:
            if archive.testzip() is not None:
                raise ValueError("Output ZIP validation failed.")
        os.replace(partial, destination)
    except OSError as exc:
        raise Problem(507, "PACKAGE_WRITE_FAILED", "Could not finish the result ZIP.") from exc
    finally:
        partial.unlink(missing_ok=True)
