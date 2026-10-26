from contextlib import closing

import numpy as np
import pytest
from PIL import Image

from localraw import conversion
from localraw.models import ConversionSettings
from tests.unit.test_conversion import FakeRaw


@pytest.mark.parametrize("flip", [0, 6])
def test_png_keeps_full_normalized_srgb_pixels_and_jpeg_preview(tmp_path, monkeypatch, flip):
    class Raw(FakeRaw):
        pass

    Raw.flip = flip
    monkeypatch.setattr(conversion.rawpy, "RawPy", Raw)
    target = tmp_path / "output.png"
    result = conversion.convert(
        tmp_path / "source.cr3",
        target,
        ConversionSettings(conversion="cr3_to_png"),
        {"max_pixels": 100, "min_free_bytes": 0},
    )
    expected = (6, 8) if flip == 6 else (8, 6)
    with closing(Image.open(target)) as image:
        assert image.format == "PNG" and image.mode == "RGB" and image.size == expected
        assert image.getexif()[274] == 1 and image.info["icc_profile"]
        reference = conversion.encode_srgb(
            np.full((expected[1], expected[0], 3), 32768, dtype=np.uint16)
        )
        np.testing.assert_array_equal(np.asarray(image), reference)
    assert result["media_type"] == "image/png" and result["output_extension"] == ".png"
    assert result["preview"]
    with closing(Image.open(tmp_path / "output.preview.jpg")) as preview:
        assert preview.format == "JPEG"
    assert not list(tmp_path.glob("*.part"))
