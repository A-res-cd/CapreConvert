import hashlib
import io
import struct
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageCms

from localraw import conversion
from localraw.errors import ConversionError
from localraw.models import ConversionSettings, transition


class FakeRaw:
    """Rendering contract double, never evidence of CR3 support."""

    flip = 0
    camera_whitebalance = (2, 1, 1.5, 1)

    def __enter__(self):
        self.sizes = SimpleNamespace(width=8, height=6, flip=self.flip)
        return self

    def __exit__(self, *args):
        pass

    def open_file(self, path):
        pass

    def unpack(self):
        pass

    def postprocess(self, **values):
        type(self).parameters = values
        shape = (8, 6, 3) if self.flip in (5, 6) else (6, 8, 3)
        return np.full(shape, 32768, dtype=np.uint16)


def test_exact_srgb_transfer():
    values = conversion.linear_to_srgb(np.array([0, 0.0031308, 0.18, 1]))
    assert values == pytest.approx([0, 0.040449936, 0.46135613, 1], abs=1e-7)


def test_all_16bit_values_retain_the_previous_quantized_transfer():
    values = np.arange(65536, dtype=np.uint16).astype(np.float32) / 65535
    # Previous implementation, evaluated independently over the complete input domain.
    reference = np.rint(
        np.clip(
            np.where(values <= 0.0031308, 12.92 * values, 1.055 * values ** (1 / 2.4) - 0.055),
            0,
            1,
        )
        * 255
    ).astype(np.uint8)
    np.testing.assert_array_equal(conversion._srgb_lookup(), reference)


@pytest.mark.parametrize("quality", [70, 95, 100])
def test_tiled_transfer_preserves_exact_pixels_and_jpeg_bytes(quality, monkeypatch):
    shape = (259, 2051, 3)  # Cross both tile boundaries and leave partial edge tiles.
    linear = np.arange(np.prod(shape), dtype=np.uint16).reshape(shape)
    values = linear.astype(np.float32) / 65535
    reference = np.rint(np.clip(conversion.linear_to_srgb(values), 0, 1) * 255).astype(np.uint8)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    original_fromarray = conversion.Image.fromarray
    tile_sizes = []

    def tracked_tile(array):
        tile_sizes.append(array.shape)
        return original_fromarray(array)

    monkeypatch.setattr(conversion.Image, "fromarray", tracked_tile)
    with conversion.encode_srgb_image(linear) as actual:
        np.testing.assert_array_equal(np.asarray(actual), reference)
        expected_bytes, actual_bytes = io.BytesIO(), io.BytesIO()
        with original_fromarray(reference) as expected:
            expected.save(expected_bytes, "JPEG", quality=quality, subsampling=0, icc_profile=profile)
        actual.save(actual_bytes, "JPEG", quality=quality, subsampling=0, icc_profile=profile)
        assert actual_bytes.getvalue() == expected_bytes.getvalue()
    assert len(tile_sizes) > 1
    assert all(height <= 128 and width <= 2048 for height, width, _ in tile_sizes)


def test_cancelled_transfer_releases_the_full_pillow_buffer(monkeypatch):
    allocated = []
    original_new = conversion.Image.new

    def tracked_new(mode, size, *args, **kwargs):
        image = original_new(mode, size, *args, **kwargs)
        if size == (2051, 129):
            allocated.append(image)
        return image

    monkeypatch.setattr(conversion.Image, "new", tracked_new)
    calls = iter((False, True))
    with pytest.raises(ConversionError, match="cancelled"):
        conversion.encode_srgb_image(np.zeros((129, 2051, 3), dtype=np.uint16), lambda: next(calls))
    assert len(allocated) == 1
    with pytest.raises(ValueError, match="closed image"):
        allocated[0].getpixel((0, 0))


def test_encoding_failure_releases_the_full_pillow_buffer(tmp_path, monkeypatch):
    monkeypatch.setattr(conversion.rawpy, "RawPy", FakeRaw)
    original_transfer = conversion.encode_srgb_image
    allocated = []

    def tracked_transfer(*args):
        image = original_transfer(*args)
        allocated.append(image)
        return image

    monkeypatch.setattr(conversion, "encode_srgb_image", tracked_transfer)
    monkeypatch.setattr(
        conversion.Image.Image,
        "save",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("encoding failure")),
    )
    with pytest.raises(OSError, match="encoding failure"):
        conversion.convert(
            tmp_path / "source.cr3",
            tmp_path / "output.jpg",
            ConversionSettings(),
            {"max_pixels": 100, "min_free_bytes": 0},
        )
    assert len(allocated) == 1
    with pytest.raises(ValueError, match="closed image"):
        allocated[0].getpixel((0, 0))
    assert not (tmp_path / "output.jpg").exists()
    assert not list(tmp_path.glob("*.part"))


def test_full_validation_pixels_are_released_before_creating_previews(tmp_path, monkeypatch):
    monkeypatch.setattr(conversion.rawpy, "RawPy", FakeRaw)
    original_open = conversion.Image.open
    validated = []

    def tracked_open(path):
        image = original_open(path)
        if str(path).endswith(".jpg.part"):
            validated.append(image)
        return image

    def preview_after_release(*args):
        assert len(validated) == 2
        for image in validated:
            with pytest.raises(ValueError, match="closed image"):
                image.getpixel((0, 0))
        return None

    monkeypatch.setattr(conversion.Image, "open", tracked_open)
    monkeypatch.setattr(conversion, "create_previews", preview_after_release)
    conversion.convert(
        tmp_path / "source.cr3",
        tmp_path / "output.jpg",
        ConversionSettings(),
        {"max_pixels": 100, "min_free_bytes": 0},
    )


def test_embedded_profile_transfer_matches_encoded_srgb():
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    count = struct.unpack_from(">I", profile, 128)[0]
    tags = {
        profile[132 + 12 * i : 136 + 12 * i]: struct.unpack_from(">II", profile, 136 + 12 * i)
        for i in range(count)
    }
    linear = np.array([0, 0.001, 0.0031308, 0.18, 0.5, 1])
    encoded = conversion.linear_to_srgb(linear)
    for tag in (b"rTRC", b"gTRC", b"bTRC"):
        offset, size = tags[tag]
        assert profile[offset : offset + 4] == b"para"
        assert struct.unpack_from(">H", profile, offset + 8)[0] == 3
        gamma, a, b, c, d = [
            struct.unpack_from(">i", profile, pos)[0] / 65536
            for pos in range(offset + 12, offset + size, 4)
        ]
        decoded = np.where(encoded >= d, (a * encoded + b) ** gamma, c * encoded)
        assert decoded == pytest.approx(linear, abs=3e-5)  # ICC s15Fixed16 quantization.


@pytest.mark.parametrize("flip,dimensions", [(0, (8, 6)), (3, (8, 6)), (5, (6, 8)), (6, (6, 8))])
def test_render_contract_and_orientation(tmp_path, monkeypatch, flip, dimensions):
    monkeypatch.setattr(conversion.rawpy, "RawPy", FakeRaw)
    monkeypatch.setattr(FakeRaw, "flip", flip)
    source = tmp_path / "photo.CR3"
    source.write_bytes(b"explicit rendering double")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    target = tmp_path / "output.jpg"
    stages, admission = [], []
    result = conversion.convert(
        source,
        target,
        ConversionSettings(),
        {"max_pixels": 120_000_000, "min_free_bytes": 0},
        stages.append,
        admission.append,
    )
    assert admission == [48]
    assert stages == ["decoding", "encoding", "validating"]
    assert (result["width"], result["height"]) == dimensions
    assert FakeRaw.parameters["gamma"] == (1, 1)
    assert FakeRaw.parameters["half_size"] is False
    assert FakeRaw.parameters["use_camera_wb"] is True
    with Image.open(target) as image:
        assert image.size == dimensions and image.getexif()[274] == 1
        assert image.info["icc_profile"] and image.layer[0][1:3] == (1, 1)
        assert image.getpixel((0, 0)) == pytest.approx((188, 188, 188), abs=1)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    assert not list(tmp_path.glob("*.part"))


def test_invalid_wb_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(conversion.rawpy, "RawPy", FakeRaw)
    monkeypatch.setattr(FakeRaw, "camera_whitebalance", [0, 0, 0, 0])
    result = conversion.convert(
        tmp_path / "x",
        tmp_path / "x.jpg",
        ConversionSettings(),
        {"max_pixels": 100, "min_free_bytes": 0},
    )
    assert any("white balance" in warning for warning in result["warnings"])
    assert FakeRaw.parameters["use_auto_wb"] is True


def test_corrupt_real_decoder_no_output_and_original_unchanged(tmp_path):
    source, output = tmp_path / "bad.CR3", tmp_path / "bad.jpg"
    source.write_bytes(b"not a RAW file")
    before = source.read_bytes()
    with pytest.raises(ConversionError, match="corrupt or unsupported"):
        conversion.convert(
            source, output, ConversionSettings(), {"max_pixels": 120_000_000, "min_free_bytes": 0}
        )
    assert source.read_bytes() == before
    assert not output.exists() and not list(tmp_path.glob("*.part"))


def test_failed_validation_never_publishes(tmp_path, monkeypatch):
    monkeypatch.setattr(conversion.rawpy, "RawPy", FakeRaw)
    monkeypatch.setattr(conversion.Image, "open", lambda _: (_ for _ in ()).throw(ValueError("bad")))
    with pytest.raises(ValueError):
        conversion.convert(
            tmp_path / "x",
            tmp_path / "x.jpg",
            ConversionSettings(),
            {"max_pixels": 100, "min_free_bytes": 0},
        )
    assert not (tmp_path / "x.jpg").exists() and not list(tmp_path.glob("*.part"))


def test_illegal_transitions():
    with pytest.raises(ValueError):
        transition({"state": "completed"}, "converting")
    with pytest.raises(ValueError):
        transition({"state": "decoding"}, "succeeded", file=True)
