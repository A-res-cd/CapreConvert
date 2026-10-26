"""Bounded optional ExifTool extraction and conservative EXIF mapping."""

import json
import math
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import ExifTags, Image
from PIL.TiffImagePlugin import IFDRational

FIELDS = {
    "Make": 271,
    "Model": 272,
    "Artist": 315,
    "Copyright": 33432,
    "DateTimeOriginal": 36867,
    "OffsetTimeOriginal": 36881,
    "ExposureTime": 33434,
    "FNumber": 33437,
    "ISO": 34855,
    "FocalLength": 37386,
    "LensModel": 42036,
    "LensMake": 42035,
}
RATIONAL = {"ExposureTime", "FNumber", "FocalLength"}


def executable(configured: str | Path | None = None):
    if configured:
        return str(configured) if Path(configured).is_file() else None
    return shutil.which("exiftool")


def _read(exe, source, gps):
    tags = list(FIELDS) + (["GPSLatitude", "GPSLongitude", "GPSAltitude"] if gps else [])
    with tempfile.TemporaryFile(dir=source.parent) as result:
        process = subprocess.Popen(
            [exe, "-json", "-n", *["-" + key for key in tags], str(source)],
            stdout=result,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        start = time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic() - start > 10 or result.tell() > 256 * 1024:
                    raise ValueError("metadata extraction limit")
                time.sleep(0.02)
            if process.returncode != 0:
                raise ValueError("metadata extraction failed")
            result.seek(0)
            data = result.read(256 * 1024 + 1)
            if len(data) > 256 * 1024:
                raise ValueError("metadata too large")
            return json.loads(data)[0]
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()


def _gps_coordinate(value):
    value = abs(float(value))
    degrees = int(value)
    minutes = int((value - degrees) * 60)
    seconds = (value - degrees - minutes / 60) * 3600
    return tuple(IFDRational(n) for n in (degrees, minutes, seconds))


def build_exif(source: Path, settings, configured=None):
    exif = Image.Exif()
    exif[274] = 1
    warnings = []
    if not settings.preserve_metadata:
        return exif, warnings
    exe = executable(configured)
    if not exe:
        return exif, ["Metadata requested: ExifTool unavailable; capture and camera tags omitted."]
    try:
        metadata = _read(exe, source, settings.include_gps)
        camera = {}
        for field, tag in FIELDS.items():
            value = metadata.get(field)
            if value is None:
                continue
            try:
                if field in RATIONAL:
                    value = float(value)
                    if not math.isfinite(value) or value <= 0:
                        raise ValueError("invalid rational")
                    value = IFDRational(value)
                elif field == "ISO":
                    value = int(value)
                    if not 0 < value < 65536:
                        raise ValueError("invalid ISO")
                else:
                    original = str(value)
                    value = original[:512].encode("ascii", "replace").decode("ascii")
                    if value != original:
                        warnings.append(
                            f"Metadata field {field} was shortened or contained unsupported text."
                        )
                (camera if tag >= 33434 else exif)[tag] = value
            except (TypeError, ValueError, OverflowError):
                warnings.append(f"Metadata field {field} could not be preserved.")
        camera[40961] = 1  # EXIF ColorSpace sRGB
        exif[ExifTags.IFD.Exif] = camera
        if settings.include_gps and "GPSLatitude" in metadata and "GPSLongitude" in metadata:
            latitude, longitude = float(metadata["GPSLatitude"]), float(metadata["GPSLongitude"])
            if not (
                math.isfinite(latitude)
                and math.isfinite(longitude)
                and abs(latitude) <= 90
                and abs(longitude) <= 180
            ):
                raise ValueError("invalid GPS")
            gps = {
                0: b"\x02\x03\x00\x00",
                1: "N" if latitude >= 0 else "S",
                2: _gps_coordinate(latitude),
                3: "E" if longitude >= 0 else "W",
                4: _gps_coordinate(longitude),
            }
            if "GPSAltitude" in metadata:
                altitude = float(metadata["GPSAltitude"])
                if math.isfinite(altitude):
                    gps[5], gps[6] = (0 if altitude >= 0 else 1), IFDRational(abs(altitude))
            exif[ExifTags.IFD.GPSInfo] = gps
        exif.tobytes()  # Fail early and fall back if a mapped value cannot be encoded.
        if not any(field in metadata for field in FIELDS):
            warnings.append("No supported capture metadata found in this CR3.")
        if settings.include_gps and not all(
            field in metadata for field in ("GPSLatitude", "GPSLongitude")
        ):
            warnings.append("GPS requested but no supported latitude/longitude tags were found.")
        warnings.append(
            "Metadata uses supported fields only; private camera tags and thumbnails omitted."
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError):
        exif = Image.Exif()
        exif[274] = 1
        warnings.append("Metadata extraction or mapping failed; image converted without capture tags.")
    return exif, warnings
