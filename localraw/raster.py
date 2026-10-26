"""Supervised static raster conversion. Never imported by HTTP handlers."""

import io
import os
import shutil
import warnings as warning_module
from contextlib import ExitStack

from PIL import ExifTags, Image, ImageCms, ImageOps

from .errors import ConversionError
from .formats import format_for
from .storage import file_hash

PRESETS = {"smaller": (80, 75, 9), "balanced": (90, 85, 6), "high": (95, 95, 3)}
FORMATS = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}


def raster_budget(pixels):
    # Source, oriented/colour/alpha, codec scratch and validating buffers, including WebP.
    return max(256 * 1024**2, 128 * 1024**2 + pixels * 40)


class BoundedWriter:
    def __init__(self, stream, path, maximum, reserve):
        self.stream, self.path, self.maximum, self.reserve = stream, path, maximum, reserve
        self.count = 0

    def write(self, data):
        if self.count + len(data) > self.maximum:
            raise ConversionError("Output exceeds its configured byte limit.")
        if shutil.disk_usage(self.path.parent).free < self.reserve + len(data):
            raise ConversionError("Not enough free disk space for output.")
        count = self.stream.write(data)
        self.count += count
        return count

    def flush(self):
        self.stream.flush()

    def tell(self):
        return self.stream.tell()


class HeaderReader:
    """Bound bytes returned by Pillow header inspection, before pixel admission."""

    def __init__(self, stream, maximum):
        self.stream, self.maximum, self.count = stream, maximum, 0

    def read(self, count=-1):
        remaining = self.maximum - self.count
        if count < 0 or count > remaining:
            raise ConversionError("Image headers exceed the inspection byte limit.")
        data = self.stream.read(count)
        self.count += len(data)
        return data

    def seek(self, *args):
        return self.stream.seek(*args)

    def tell(self):
        return self.stream.tell()


def webp_header(stream, size, header_limit):
    header = stream.read(12)
    if int.from_bytes(header[4:8], "little") + 8 != size:
        raise ConversionError("WebP RIFF size is invalid or truncated.")
    count = 0
    while stream.tell() + 8 <= size and count < 10000:
        chunk = stream.read(8)
        kind, length = chunk[:4], int.from_bytes(chunk[4:], "little")
        if stream.tell() + length > size:
            raise ConversionError("WebP chunk is truncated.")
        count += 1
        if count * 18 > header_limit:
            raise ConversionError("WebP header inspection limit exceeded.")
        if kind == b"VP8X" and length >= 10:
            data = stream.read(10)
            if data[0] & 2:
                raise ConversionError("Animated WebP unsupported; export a static frame first.")
            return 1 + int.from_bytes(data[4:7], "little"), 1 + int.from_bytes(data[7:10], "little")
        if kind == b"VP8 " and length >= 10:
            data = stream.read(10)
            if data[3:6] != b"\x9d\x01\x2a":
                raise ConversionError("Invalid WebP frame header.")
            return int.from_bytes(data[6:8], "little") & 0x3FFF, int.from_bytes(
                data[8:10], "little"
            ) & 0x3FFF
        if kind == b"VP8L" and length >= 5:
            data = stream.read(5)
            if data[0] != 0x2F:
                raise ConversionError("Invalid lossless WebP header.")
            value = int.from_bytes(data[1:5], "little")
            return (value & 0x3FFF) + 1, ((value >> 14) & 0x3FFF) + 1
        stream.seek(length + (length % 2), 1)
    raise ConversionError("WebP dimensions unavailable within header limits.")


def check_cancelled(cancelled):
    if cancelled():
        raise ConversionError("Conversion cancelled.")


def effective_settings(settings):
    options = settings.raster
    jpeg, webp, png = PRESETS[options.preset]
    return {
        **options.model_dump(),
        "jpeg_quality": options.jpeg_quality or jpeg,
        "webp_quality": options.webp_quality or webp,
        "png_compression": png if options.png_compression is None else options.png_compression,
        "upscale": False,
        "colour_space": "sRGB",
    }


def metadata(image, settings, notices):
    result = Image.Exif()
    result[274] = 1
    if not settings.preserve_metadata:
        return result
    try:
        original = image.getexif()
        # Conservative capture whitelist. Never dimensions, embedded thumbnails or arbitrary tags.
        for tag in (271, 272, 315, 33432):
            value = original.get(tag)
            if isinstance(value, str):
                result[tag] = value[:512].encode("ascii", "replace").decode("ascii")
        capture = original.get_ifd(ExifTags.IFD.Exif)
        kept = {}
        for tag in (36867, 36881, 33434, 33437, 34855, 37386, 42036, 42035):
            value = capture.get(tag)
            if isinstance(value, str):
                kept[tag] = value[:512].encode("ascii", "replace").decode("ascii")
            elif isinstance(value, (int, float)) or hasattr(value, "numerator"):
                if len(str(value)) < 128:
                    kept[tag] = value
        if kept:
            result[ExifTags.IFD.Exif] = kept
        if settings.include_gps:
            gps = original.get_ifd(ExifTags.IFD.GPSInfo)
            kept_gps = {key: value for key, value in gps.items() if key in (0, 1, 2, 3, 4, 5, 6)}
            if kept_gps:
                result[ExifTags.IFD.GPSInfo] = kept_gps
        if len(result.tobytes()) > 16384:
            raise ValueError("metadata size")
    except Exception:
        result = Image.Exif()
        result[274] = 1
        notices.append("Capture metadata could not be retained; unsafe or invalid tags omitted.")
    return result


def normalized(image, stack, notices):
    alpha = (
        stack.enter_context(image.convert("RGBA")).getchannel("A")
        if "A" in image.getbands() or "transparency" in image.info
        else None
    )
    if alpha:
        stack.callback(alpha.close)
    if image.mode not in {"RGB", "RGBA", "L", "LA", "P", "CMYK"}:
        notices.append("High precision or unusual source mode normalized to 8-bit RGB.")
    profile = image.info.get("icc_profile")
    base = image if image.mode in ("RGB", "CMYK", "L") else stack.enter_context(image.convert("RGB"))
    if profile:
        try:
            rgb = stack.enter_context(
                ImageCms.profileToProfile(
                    base,
                    ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            )
        except (OSError, ValueError, ImageCms.PyCMSError):
            notices.append("Invalid or incompatible ICC profile; mode conversion assumes sRGB.")
            rgb = stack.enter_context(base.convert("RGB"))
    else:
        notices.append(
            "No ICC profile: RGB/grayscale assumed sRGB; CMYK uses Pillow's deterministic fallback."
        )
        rgb = stack.enter_context(base.convert("RGB"))
    if alpha:
        rgb.putalpha(alpha)
    return rgb


def image_derivatives(image, destination, limits):
    """Only called with committed output pixels. Reduced PNGs preserve transparent areas."""
    published, details = [], {}
    try:
        with image.copy() as reduced:
            for kind, edge, budget in (("preview", 1280, 2 * 1024**2), ("thumbnail", 320, 256 * 1024)):
                reduced.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                target = destination.with_name(destination.stem + f".{kind}.png")
                part = target.with_suffix(".png.part")
                try:
                    with part.open("wb") as stream:
                        reduced.save(
                            BoundedWriter(stream, part, budget, limits["min_free_bytes"]),
                            format="PNG",
                            compress_level=3,
                        )
                        stream.flush()
                        os.fsync(stream.fileno())
                    with Image.open(part) as checked:
                        checked.load()
                        if checked.size != reduced.size or checked.format != "PNG":
                            raise ConversionError("Preview validation failed.")
                    os.replace(part, target)
                    published.append(target)
                    details[kind] = {
                        "width": reduced.width,
                        "height": reduced.height,
                        "size_bytes": target.stat().st_size,
                        "sha256": file_hash(target),
                        "extension": ".png",
                    }
                finally:
                    part.unlink(missing_ok=True)
        return {**details["preview"], "thumbnail": details["thumbnail"]}
    except BaseException:
        for target in published:
            target.unlink(missing_ok=True)
        raise


def convert_raster(
    source,
    destination,
    settings,
    limits,
    progress=lambda stage: None,
    admit=lambda pixels: None,
    cancelled=lambda: False,
):
    descriptor = format_for(settings)
    source_format, output_format = (FORMATS[key] for key in settings.conversion.split("_to_"))
    if destination.exists() or source.resolve() == destination.resolve():
        raise ConversionError("Output already exists or would replace its input.")
    source_bytes = source.stat().st_size
    if not 0 < source_bytes <= limits["raster_max_bytes"]:
        raise ConversionError("Image input exceeds its byte limit or is empty.")
    options, notices = effective_settings(settings), []
    part = destination.with_suffix(destination.suffix + ".part")
    try:
        check_cancelled(cancelled)
        progress("decoding")
        with warning_module.catch_warnings():
            warning_module.simplefilter("error", Image.DecompressionBombWarning)
            with source.open("rb") as stream:
                prefix = stream.read(12)
                stream.seek(0)
                if prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
                    # Pillow WebP opens by reading the complete encoded stream. Inspect
                    # RIFF dimensions first, authorize before entering that decoder.
                    if source_format != "WEBP":
                        raise ConversionError("Actual format is WebP; choose its matching converter.")
                    width, height = webp_header(stream, source_bytes, limits["raster_header_max_bytes"])
                else:
                    with Image.open(HeaderReader(stream, limits["raster_header_max_bytes"])) as header:
                        width, height = header.size
                        if header.format != source_format:
                            raise ConversionError(
                                f"Actual image format is {header.format}; choose the matching input converter."
                            )
                        if getattr(header, "n_frames", 1) != 1 or getattr(header, "is_animated", False):
                            raise ConversionError(
                                "Animated or multiframe images are unsupported; export a static frame first."
                            )
                if (
                    min(width, height) < 1
                    or max(width, height) > limits["raster_max_dimension"]
                    or width * height > limits["max_pixels"]
                ):
                    raise ConversionError(
                        "Image dimensions exceed the configured pixel/dimension limit."
                    )
            admit(width * height)
            with ExitStack() as stack:
                image = stack.enter_context(Image.open(source))
                if image.format != source_format or image.size != (width, height):
                    raise ConversionError("Decoded format/dimensions do not match inspected headers.")
                if getattr(image, "n_frames", 1) != 1 or getattr(image, "is_animated", False):
                    raise ConversionError(
                        "Animated or multiframe images are unsupported; export a static frame first."
                    )
                exif = metadata(image, settings, notices)
                image.load()
                oriented = stack.enter_context(ImageOps.exif_transpose(image))
                rgb = normalized(oriented, stack, notices)
                ratio = min(
                    1,
                    (options["max_width"] or rgb.width) / rgb.width,
                    (options["max_height"] or rgb.height) / rgb.height,
                )
                if ratio < 1:
                    rgb = stack.enter_context(
                        rgb.resize(
                            (max(1, int(rgb.width * ratio)), max(1, int(rgb.height * ratio))),
                            Image.Resampling.LANCZOS,
                        )
                    )
                if output_format == "WEBP" and rgb.mode == "RGBA":
                    with rgb.getchannel("A") as alpha:
                        opaque = alpha.getextrema() == (255, 255)
                    if opaque:
                        # WebP omits a fully opaque alpha channel. Normalize that
                        # explicitly so validation expects its actual decoded mode.
                        rgb = stack.enter_context(rgb.convert("RGB"))
                if output_format == "JPEG" and rgb.mode == "RGBA":
                    background = stack.enter_context(Image.new("RGB", rgb.size, options["background"]))
                    with rgb.getchannel("A") as alpha:
                        background.paste(rgb, mask=alpha)
                    rgb = background
                if output_format == "WEBP" and max(rgb.size) > 16383:
                    raise ConversionError(
                        "WebP supports dimensions up to 16383 pixels; choose a resize bound."
                    )
                check_cancelled(cancelled)
                progress("encoding")
                codec = (
                    {"quality": options["jpeg_quality"], "subsampling": 0, "optimize": False}
                    if output_format == "JPEG"
                    else {"compress_level": options["png_compression"]}
                    if output_format == "PNG"
                    else {
                        "quality": options["webp_quality"],
                        "lossless": options["webp_lossless"],
                        "method": 4,
                        "exact": True,
                    }
                )
                icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
                with part.open("wb") as stream:
                    rgb.save(
                        BoundedWriter(
                            stream, part, limits["raster_output_max_bytes"], limits["min_free_bytes"]
                        ),
                        format=output_format,
                        exif=exif.tobytes(),
                        icc_profile=icc,
                        **codec,
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
                expected, mode = rgb.size, rgb.mode
            progress("validating")
            with Image.open(part) as checked:
                checked.load()
                if checked.format != output_format or checked.size != expected or checked.mode != mode:
                    raise ConversionError("Encoded output validation failed.")
                check_cancelled(cancelled)
                os.replace(part, destination)
                preview = None
                try:
                    preview = image_derivatives(checked, destination, limits)
                except Exception:
                    notices.append("Preview failed; committed output remains downloadable.")
        size = destination.stat().st_size
        if output_format == "JPEG" or (output_format == "WEBP" and not options["webp_lossless"]):
            notices.append("Lossy recompression cannot restore source detail.")
        return {
            "width": expected[0],
            "height": expected[1],
            "source_width": width,
            "source_height": height,
            "source_bytes": source_bytes,
            "size_bytes": size,
            "savings_percent": 100 * (source_bytes - size) / source_bytes,
            "effective_settings": options,
            "warnings": notices,
            "sha256": file_hash(destination),
            "preview": preview,
            "output_extension": descriptor.output_extension,
            "media_type": descriptor.media_type,
        }
    except ConversionError:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ConversionError("Image exceeds Pillow's safe decompression limit.") from exc
    except (OSError, ValueError, SyntaxError) as exc:
        raise ConversionError("Image is corrupt, truncated or unsupported.") from exc
    finally:
        part.unlink(missing_ok=True)
