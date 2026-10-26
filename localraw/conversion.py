"""Full visible RAW render, exact sRGB transfer and atomic validated JPEG publication.

Imported only inside workers during real jobs. Tests use an explicit decoder double.
"""

import math
import os
import shutil
from contextlib import closing
from pathlib import Path

import numpy as np
import rawpy
from PIL import Image, ImageCms

from .config import PREVIEW_MAX_BYTES, THUMBNAIL_MAX_BYTES
from .errors import ConversionError
from .formats import format_for, output_budget
from .metadata import build_exif
from .storage import file_hash


def linear_to_srgb(linear):
    """IEC sRGB encoding, with a linear toe (input [0,1], output [0,1])."""
    return np.where(linear <= 0.0031308, 12.92 * linear, 1.055 * np.power(linear, 1 / 2.4) - 0.055)


def encode_srgb(linear16):
    lookup = _srgb_lookup()
    rgb = np.empty(linear16.shape, dtype=np.uint8)
    for row in range(0, linear16.shape[0], 128):
        rgb[row : row + 128] = lookup[linear16[row : row + 128]]
    return rgb


def _srgb_lookup():
    # Every uint16 input is represented. Match the previous float32 arithmetic exactly.
    values = np.arange(65536, dtype=np.float32) / 65535
    return np.rint(np.clip(linear_to_srgb(values), 0, 1) * 255).astype(np.uint8)


def encode_srgb_image(linear16, cancelled=lambda: False):
    """Fill Pillow from bounded tiles, without an additional full-size RGB8 array."""
    height, width = linear16.shape[:2]
    lookup = _srgb_lookup()
    image = Image.new("RGB", (width, height))
    try:
        for row in range(0, height, 128):
            for column in range(0, width, 2048):
                if cancelled():
                    raise ConversionError("Conversion cancelled.")
                values = lookup[linear16[row : row + 128, column : column + 2048]]
                with closing(Image.fromarray(values)) as tile:
                    image.paste(tile, (column, row))
        return image
    except BaseException:
        image.close()
        raise


class BoundedOutput:
    """Pillow writes through this wrapper, so limits are checked during encoding."""

    def __init__(self, stream, path, budget, free_reserve):
        self.stream, self.path, self.budget, self.free_reserve = stream, path, budget, free_reserve
        self.count = 0

    def write(self, data):
        if self.count + len(data) > self.budget:
            raise ConversionError("Encoded output exceeds its reserved capacity.")
        if shutil.disk_usage(self.path.parent).free < self.free_reserve + len(data):
            raise ConversionError("Not enough free disk space to finish this image.")
        count = self.stream.write(data)
        self.count += count
        return count

    def flush(self):
        self.stream.flush()

    def tell(self):
        return self.stream.tell()


def create_previews(source: Path, min_free_bytes=0):
    """Run inside a supervised image worker; derivatives never copy capture/GPS EXIF."""
    published = []
    details = {}
    try:
        with closing(Image.open(source)) as image:
            # Full-size JPEG has already been decoded for validation. Use JPEG's native
            # scaled decoding for derivatives instead of allocating that image again.
            image.draft("RGB", (1280, 1280))
            profile = (
                image.info.get("icc_profile")
                or ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            )
            exif = Image.Exif()
            exif[274] = 1  # Source pixels were already normalized; never rotate again.
            for kind, edge, budget in (
                ("preview", 1280, PREVIEW_MAX_BYTES),
                ("thumbnail", 320, THUMBNAIL_MAX_BYTES),
            ):
                image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                target = source.with_name(source.stem + f".{kind}.jpg")
                partial = target.with_suffix(".jpg.part")
                try:
                    if target.exists():
                        raise ConversionError("Preview output already exists.")
                    with partial.open("wb") as stream:
                        image.save(
                            BoundedOutput(stream, partial, budget, min_free_bytes),
                            format="JPEG",
                            quality=82,
                            subsampling=2,
                            exif=exif,
                            icc_profile=profile,
                        )
                        stream.flush()
                        os.fsync(stream.fileno())
                    with closing(Image.open(partial)) as checked:
                        checked.load()
                        if checked.format != "JPEG" or checked.size != image.size:
                            raise ConversionError("Preview validation failed.")
                    os.replace(partial, target)
                    published.append(target)
                    details[kind] = {
                        "width": image.width,
                        "height": image.height,
                        "size_bytes": target.stat().st_size,
                        "sha256": file_hash(target),
                    }
                finally:
                    partial.unlink(missing_ok=True)
        return {**details["preview"], "thumbnail": details["thumbnail"]}
    except BaseException:
        for target in published:
            target.unlink(missing_ok=True)
        raise


def convert(
    source: Path,
    destination: Path,
    settings,
    limits,
    progress=lambda stage: None,
    admit=lambda pixels: None,
    cancelled=lambda: False,
):
    descriptor = format_for(settings)
    encoding = "PNG" if descriptor.output_extension == ".png" else "JPEG"
    part = destination.with_suffix(destination.suffix + ".part")
    warnings = []
    linear = None
    try:
        if cancelled():
            raise ConversionError("Conversion cancelled.")
        progress("decoding")
        with rawpy.RawPy() as raw:
            raw.open_file(str(source))  # Inspect in the already isolated/memory-monitored worker.
            sizes = raw.sizes
            width, height = int(sizes.width), int(sizes.height)
            pixels = width * height
            if min(width, height) <= 0 or pixels > limits["max_pixels"]:
                raise ConversionError("Visible image dimensions exceed the configured limit.")
            admit(pixels)  # Parent authorizes memory and disk before unpack/postprocess.
            expected = (height, width) if sizes.flip in (5, 6) else (width, height)
            raw.unpack()
            auto = settings.white_balance == "auto"
            if not auto:
                wb = raw.camera_whitebalance
                if not wb or len(wb) < 3 or not all(math.isfinite(x) and x > 0 for x in wb[:3]):
                    auto = True
                    warnings.append("Invalid camera white balance; auto white balance used.")
            linear = raw.postprocess(
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                half_size=False,
                use_camera_wb=not auto,
                use_auto_wb=auto,
                output_color=rawpy.ColorSpace.sRGB,
                output_bps=16,
                gamma=(1, 1),
                no_auto_bright=True,
                bright=1.0,
                median_filter_passes=0,
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
                user_flip=None,
            )
        if (linear.shape[1], linear.shape[0]) != expected or linear.shape[2:] != (3,):
            raise ConversionError("Decoder dimensions do not match the full visible image.")
        if cancelled():
            raise ConversionError("Conversion cancelled.")
        progress("encoding")
        with closing(encode_srgb_image(linear, cancelled)) as image:
            linear = None
            exif, metadata_warnings = build_exif(source, settings, limits.get("exiftool"))
            warnings.extend(metadata_warnings)
            profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ConversionError("Output already exists.")
            with part.open("wb") as stream:
                output = BoundedOutput(
                    stream,
                    part,
                    output_budget(pixels, descriptor.output_extension),
                    limits["min_free_bytes"],
                )
                codec_options = (
                    {"compress_level": 6}
                    if encoding == "PNG"
                    else {"quality": settings.jpeg_quality, "subsampling": 0, "optimize": False}
                )
                image.save(
                    output,
                    format=encoding,
                    icc_profile=profile,
                    exif=exif,
                    **codec_options,
                )
                stream.flush()
                os.fsync(stream.fileno())
        progress("validating")
        with closing(Image.open(part)) as result:
            if result.format != encoding or result.size != expected or result.mode != "RGB":
                raise ConversionError("Encoded image validation failed.")
            result.verify()
        with closing(Image.open(part)) as result:
            result.load()
        if cancelled():
            raise ConversionError("Conversion cancelled.")
        os.replace(part, destination)
        preview = None
        try:
            preview = create_previews(destination, limits["min_free_bytes"])
        except (OSError, ValueError, ConversionError):
            warnings.append(
                "Preview could not be prepared; the full-resolution image is still available."
            )
        return {
            "width": expected[0],
            "height": expected[1],
            "warnings": warnings,
            "size_bytes": destination.stat().st_size,
            "sha256": file_hash(destination),
            "preview": preview,
            "output_extension": descriptor.output_extension,
            "media_type": descriptor.media_type,
        }
    except rawpy.LibRawError as exc:
        raise ConversionError("CR3 is corrupt or unsupported by this LibRaw build.") from exc
    finally:
        linear = None
        part.unlink(missing_ok=True)
