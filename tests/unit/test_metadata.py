from PIL import ExifTags, Image

from localraw.metadata import build_exif
from localraw.models import ConversionSettings


def test_supported_mapping_orientation_and_gps_opt_in(tmp_path, monkeypatch):
    metadata = {
        "Make": "Canon",
        "Model": "Camera",
        "ExposureTime": 1 / 125,
        "FNumber": 2.8,
        "ISO": 400,
        "FocalLength": 50,
        "DateTimeOriginal": "2024:01:02 03:04:05",
        "OffsetTimeOriginal": "+08:00",
        "Artist": "Photographer",
        "Copyright": "Owner",
        "GPSLatitude": -14.5,
        "GPSLongitude": 121.1,
        "GPSAltitude": 20,
        "Orientation": 6,
        "MakerNotes": "must not copy",
    }
    monkeypatch.setattr("localraw.metadata.executable", lambda _: "controlled")
    monkeypatch.setattr("localraw.metadata._read", lambda *args: metadata)
    exif, _ = build_exif(tmp_path / "controlled.cr3", ConversionSettings())
    assert exif[274] == 1 and exif[271] == "Canon"
    assert 34853 not in exif and 37500 not in exif
    serialized = Image.Exif()
    serialized.load(exif.tobytes())
    camera = serialized.get_ifd(ExifTags.IFD.Exif)
    assert float(camera[33434]) == 1 / 125 and camera[34855] == 400
    assert 37500 not in camera
    exif, _ = build_exif(tmp_path / "controlled.cr3", ConversionSettings(include_gps=True))
    image = Image.new("RGB", (2, 2))
    path = tmp_path / "mapped.jpg"
    image.save(path, exif=exif)
    with Image.open(path) as output:
        gps = output.getexif().get_ifd(ExifTags.IFD.GPSInfo)
        assert gps[1] == "S" and gps[3] == "E" and len(gps[2]) == 3
        assert output.getexif()[274] == 1


def test_metadata_missing_partial_and_failed_mapping(tmp_path, monkeypatch):
    monkeypatch.setattr("localraw.metadata.executable", lambda _: None)
    exif, warnings = build_exif(tmp_path / "controlled.cr3", ConversionSettings())
    assert warnings and exif[274] == 1
    _, warnings = build_exif(tmp_path / "controlled.cr3", ConversionSettings(preserve_metadata=False))
    assert not warnings
    monkeypatch.setattr("localraw.metadata.executable", lambda _: "controlled")
    monkeypatch.setattr("localraw.metadata._read", lambda *args: {"ExposureTime": "nan"})
    _, warnings = build_exif(tmp_path / "controlled.cr3", ConversionSettings())
    assert any("ExposureTime" in warning for warning in warnings)
