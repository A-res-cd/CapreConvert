import hashlib

import pytest
from PIL import ExifTags, Image, JpegImagePlugin

from localraw import conversion
from localraw.errors import ConversionError
from localraw.models import ConversionSettings
from tests.unit.test_conversion import FakeRaw


def test_large_preview_uses_scaled_decoder_without_full_resolution_load(tmp_path, monkeypatch):
    source = tmp_path / "full.jpg"
    with Image.new("RGB", (5536, 3692), (33, 88, 120)) as image:
        image.save(source, quality=95, subsampling=0)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    original_load = JpegImagePlugin.JpegImageFile.load
    decoded_sizes = []

    def tracked_load(image, *args, **kwargs):
        if getattr(image, "filename", None) == str(source):
            decoded_sizes.append(image.size)
        return original_load(image, *args, **kwargs)

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "load", tracked_load)
    metadata = conversion.create_previews(source)
    assert decoded_sizes
    assert all(width <= 2768 and height <= 1846 for width, height in decoded_sizes)
    assert max(metadata["width"], metadata["height"]) <= 1280
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("dimensions", [(3000, 2000), (1800, 3000), (8, 6)])
def test_bounded_derivatives_preserve_full_jpg_and_strip_capture_metadata(tmp_path, dimensions):
    source = tmp_path / "source.jpg"
    exif = Image.Exif()
    exif[274], exif[271] = 1, "Canon"
    exif[ExifTags.IFD.GPSInfo] = {1: "N", 2: (14, 30, 0), 3: "E", 4: (121, 0, 0)}
    with Image.new("RGB", dimensions, (88, 133, 100)) as image:
        image.save(source, exif=exif)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = conversion.create_previews(source)
    for kind, edge, budget in (("preview", 1280, 2 * 1024**2), ("thumbnail", 320, 256 * 1024)):
        path = tmp_path / f"source.{kind}.jpg"
        details = metadata if kind == "preview" else metadata["thumbnail"]
        with Image.open(path) as image:
            image.load()
            assert image.mode == "RGB" and image.format == "JPEG"
            assert max(image.size) <= edge
            assert image.size == (details["width"], details["height"])
            assert image.getexif()[274] == 1
            assert 271 not in image.getexif() and ExifTags.IFD.GPSInfo not in image.getexif()
            assert image.info["icc_profile"]
            assert (image.width > image.height) == (dimensions[0] > dimensions[1])
        assert path.stat().st_size == details["size_bytes"] <= budget
        assert hashlib.sha256(path.read_bytes()).hexdigest() == details["sha256"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    assert not list(tmp_path.glob("*.part"))


def test_failed_thumbnail_never_leaves_half_derivative_pair(tmp_path, monkeypatch):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (32, 24)).save(source)
    save = Image.Image.save

    def fail_thumbnail(image, output, *args, **kwargs):
        if ".thumbnail." in output.path.name:
            raise OSError("disk failure double")
        return save(image, output, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "save", fail_thumbnail)
    with pytest.raises(OSError):
        conversion.create_previews(source)
    assert source.exists()
    assert not (tmp_path / "photo.preview.jpg").exists()
    assert not list(tmp_path.glob("*.part"))


def test_preview_byte_limit_cleans_partials(tmp_path, monkeypatch):
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (32, 24)).save(source)
    monkeypatch.setattr(conversion, "PREVIEW_MAX_BYTES", 16)
    with pytest.raises(ConversionError, match="capacity"):
        conversion.create_previews(source)
    assert list(tmp_path.glob("*.jpg")) == [source]
    assert not list(tmp_path.glob("*.part"))


def test_unavailable_preview_does_not_discard_valid_full_jpg(tmp_path, monkeypatch):
    monkeypatch.setattr(conversion.rawpy, "RawPy", FakeRaw)
    monkeypatch.setattr(
        conversion,
        "create_previews",
        lambda *args: (_ for _ in ()).throw(OSError("preview unavailable")),
    )
    target = tmp_path / "full.jpg"
    result = conversion.convert(
        tmp_path / "source.cr3", target, ConversionSettings(), {"max_pixels": 100, "min_free_bytes": 0}
    )
    assert result["preview"] is None and target.exists()
    assert any("Preview could not be prepared" in warning for warning in result["warnings"])
