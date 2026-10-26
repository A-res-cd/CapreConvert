"""Real-codec contracts for every raster conversion, normalization and rejection."""

import pytest
from PIL import Image, ImageCms

from localraw.config import Settings
from localraw.errors import ConversionError
from localraw.formats import CONVERSIONS
from localraw.models import ConversionSettings
from localraw.raster import convert_raster

RASTER = [key for key, value in CONVERSIONS.items() if value.engine == "raster"]


def run(tmp_path, key, mode="RGB", options=None, size=(40, 20), exif=None, profile=None):
    source, target = tmp_path / "source.input", tmp_path / ("result" + CONVERSIONS[key].output_extension)
    kind = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[key.split("_to_")[0]]
    colour = (
        (20, 70, 120, 0)
        if mode == "RGBA"
        else (20, 70, 120)
        if mode == "RGB"
        else 80
        if mode in ("L", "P")
        else (20, 70, 120, 30)
    )
    with Image.new(mode, size, colour) as image:
        kwargs = {"exif": exif.tobytes()} if exif else {}
        if profile is not None:
            kwargs["icc_profile"] = profile
        image.save(source, format=kind, **kwargs)
    settings = Settings(workspace=tmp_path / "workspace", min_free_bytes=0).model_dump(mode="json")
    admissions = []
    metadata = convert_raster(
        source,
        target,
        ConversionSettings(conversion=key, raster=options or {}),
        settings,
        admit=admissions.append,
    )
    assert admissions == [size[0] * size[1]]
    assert metadata["source_bytes"] == source.stat().st_size
    assert metadata["size_bytes"] == target.stat().st_size
    assert metadata["preview"]
    return metadata, target


@pytest.mark.parametrize("key", RASTER)
def test_all_real_codecs(tmp_path, key):
    info, path = run(tmp_path, key)
    with Image.open(path) as image:
        image.load()
        assert image.size == (40, 20)
        assert image.info["icc_profile"]
        assert image.getexif()[274] == 1
    assert info["savings_percent"] == pytest.approx(
        100 * (info["source_bytes"] - info["size_bytes"]) / info["source_bytes"]
    )


@pytest.mark.parametrize("key", ["png_to_png", "png_to_webp"])
def test_alpha_and_lossless_hidden_rgb(tmp_path, key):
    _, path = run(tmp_path, key, "RGBA", {"webp_lossless": True})
    with Image.open(path) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((2, 2)) == (20, 70, 120, 0)
    with Image.open(path.with_name(path.stem + ".preview.png")) as preview:
        assert preview.mode == "RGBA"
        assert preview.getpixel((2, 2))[3] == 0
        assert not preview.getexif()


def test_rotated_resize_no_upscale_and_background(tmp_path):
    exif = Image.Exif()
    exif[274] = 6
    info, _ = run(tmp_path, "jpg_to_png", options={"max_width": 10}, exif=exif)
    assert (info["width"], info["height"]) == (10, 20)
    other = tmp_path / "other"
    other.mkdir()
    _, target = run(other, "png_to_jpg", "RGBA", {"background": "#00ff00", "max_width": 200})
    with Image.open(target) as image:
        assert image.size == (40, 20)
        assert max(abs(a - b) for a, b in zip(image.getpixel((2, 2)), (0, 255, 0), strict=True)) < 3


@pytest.mark.parametrize("mode,key", [("L", "png_to_png"), ("P", "png_to_png"), ("CMYK", "jpg_to_png")])
def test_modes_and_profile_fallback(tmp_path, mode, key):
    info, target = run(tmp_path, key, mode)
    with Image.open(target) as image:
        assert image.mode == "RGB"
    assert any("No ICC" in warning for warning in info["warnings"])


def test_profiles(tmp_path):
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    info, _ = run(tmp_path, "png_to_png", profile=profile)
    assert not any("ICC" in warning for warning in info["warnings"])
    other = tmp_path / "bad"
    other.mkdir()
    info, _ = run(other, "png_to_png", profile=b"invalid")
    assert any("Invalid" in warning for warning in info["warnings"])


@pytest.mark.parametrize(
    "failure", ["mismatch", "animated", "corrupt", "pixels", "output", "cancel", "header"]
)
def test_rejections_never_publish(tmp_path, failure):
    source, target = tmp_path / "source", tmp_path / "result.png"
    with Image.new("RGB", (40, 30)) as image:
        image.save(
            source,
            format="PNG",
            save_all=failure == "animated",
            append_images=[Image.new("RGB", (40, 30), "red")] if failure == "animated" else [],
        )
    limits = Settings(workspace=tmp_path / "ws", min_free_bytes=0).model_dump(mode="json")
    if failure == "corrupt":
        source.write_bytes(b"bad")
    if failure == "pixels":
        limits["max_pixels"] = 100
    if failure == "output":
        limits["raster_output_max_bytes"] = 10
    if failure == "header":
        limits["raster_header_max_bytes"] = 10
    with pytest.raises(ConversionError):
        convert_raster(
            source,
            target,
            ConversionSettings(conversion="jpg_to_png" if failure == "mismatch" else "png_to_png"),
            limits,
            cancelled=lambda: failure == "cancel",
        )
    assert not target.exists()
    assert not list(tmp_path.glob("*.part"))


def test_metadata_privacy_orientation_and_preview_isolation(tmp_path, monkeypatch):
    from PIL import ExifTags

    from localraw import raster

    source = tmp_path / "photo.png"
    exif = Image.Exif()
    exif[274] = 6
    exif[256] = 9999
    exif[271] = "Camera maker"
    exif[ExifTags.IFD.GPSInfo] = {1: "N", 2: (1, 2, 3), 3: "E", 4: (4, 5, 6)}
    with Image.new("RGB", (40, 20), "red") as image:
        image.save(source, exif=exif)
    limits = Settings(workspace=tmp_path / "workspace", min_free_bytes=0).model_dump(mode="json")
    for gps in (False, True):
        target = tmp_path / f"output-{gps}.png"
        info = convert_raster(
            source, target, ConversionSettings(conversion="png_to_png", include_gps=gps), limits
        )
        with Image.open(target) as output:
            assert output.size == (20, 40) and output.getexif()[274] == 1
            assert output.getexif()[271] == "Camera maker"
            assert 256 not in output.getexif()
            assert bool(output.getexif().get_ifd(ExifTags.IFD.GPSInfo)) == gps
        assert info["preview"]
    monkeypatch.setattr(
        raster, "image_derivatives", lambda *args: (_ for _ in ()).throw(OSError("failure"))
    )
    target = tmp_path / "no-preview.png"
    info = convert_raster(source, target, ConversionSettings(conversion="png_to_png"), limits)
    assert target.is_file() and info["preview"] is None
    assert any("Preview failed" in message for message in info["warnings"])


def test_palette_alpha_and_animated_webp(tmp_path):
    source = tmp_path / "palette.png"
    with Image.new("P", (30, 20), 0) as image:
        image.putpalette([20, 70, 120] + [0] * 765)
        image.info["transparency"] = 0
        image.save(source)
    limits = Settings(workspace=tmp_path / "workspace", min_free_bytes=0).model_dump(mode="json")
    target = tmp_path / "palette-output.png"
    convert_raster(source, target, ConversionSettings(conversion="png_to_png"), limits)
    with Image.open(target) as output:
        assert output.getpixel((1, 1)) == (20, 70, 120, 0)
    with Image.new("RGB", (30, 20), "red") as first, Image.new("RGB", (30, 20), "blue") as second:
        source = tmp_path / "animation.webp"
        first.save(source, save_all=True, append_images=[second], duration=100, loop=0)
    with pytest.raises(ConversionError, match="Animated"):
        convert_raster(
            source, tmp_path / "animation.png", ConversionSettings(conversion="webp_to_png"), limits
        )


def test_truncated_jpeg_and_pillow_bomb(tmp_path, monkeypatch):
    source = tmp_path / "truncated.jpg"
    with Image.new("RGB", (500, 500), "red") as image:
        image.save(source)
    payload = source.read_bytes()
    source.write_bytes(payload[: len(payload) // 2])
    limits = Settings(workspace=tmp_path / "workspace", min_free_bytes=0).model_dump(mode="json")
    with pytest.raises(ConversionError):
        convert_raster(source, tmp_path / "out.png", ConversionSettings(conversion="jpg_to_png"), limits)
    source.write_bytes(payload)
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(ConversionError, match="decompression"):
        convert_raster(source, tmp_path / "out.png", ConversionSettings(conversion="jpg_to_png"), limits)


@pytest.mark.parametrize("lossless", [False, True])
def test_opaque_rgba_to_webp_omitted_alpha_is_valid(tmp_path, lossless):
    source = tmp_path / "opaque.png"
    with Image.new("RGBA", (60, 40), (20, 70, 120, 255)) as image:
        image.save(source)
    target = tmp_path / "opaque.webp"
    info = convert_raster(
        source,
        target,
        ConversionSettings(conversion="png_to_webp", raster={"webp_lossless": lossless}),
        Settings(workspace=tmp_path / "ws", min_free_bytes=0).model_dump(mode="json"),
    )
    assert info["preview"] and target.is_file()
    with Image.open(target) as output:
        assert output.mode == "RGB"
        if lossless:
            assert output.getpixel((1, 1)) == (20, 70, 120)
