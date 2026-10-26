import pytest
from pydantic import ValidationError

from localraw.archives import OutputNames
from localraw.formats import CONVERSIONS, format_for
from localraw.models import ConversionSettings, JobRequest


def test_legacy_requests_keep_jpeg_defaults_and_settings():
    request = JobRequest(upload_ids=["legacy-upload"], settings={"jpeg_quality": 97})
    assert request.settings.conversion == "cr3_to_jpg"
    assert request.settings.jpeg_quality == 97
    assert format_for({"jpeg_quality": 97}).output_extension == ".jpg"
    assert format_for(request.settings).media_type == "image/jpeg"


@pytest.mark.parametrize("key", CONVERSIONS)
def test_format_contract_accepts_only_the_documented_modes(key):
    settings = ConversionSettings(conversion=key)
    spec = format_for(settings)
    assert spec.output_extension in {".jpg", ".png", ".webp", ".pdf", ".docx"}
    assert spec.is_raw == key.startswith("cr3_")
    with pytest.raises(ValidationError):
        ConversionSettings(conversion="../../output")


def test_format_output_names_preserve_folders_suffixes_and_case_collisions():
    names = OutputNames()
    assert names.jpeg("folder/photo.cr3", "-edit") == "folder/photo-edit.jpg"
    assert names.output("folder/photo.cr3", "-edit", ".png") == "folder/photo-edit.png"
    assert names.output("folder/PHOTO.cr3", "-edit", ".png") == "folder/PHOTO-edit__2.png"
    assert names.output("report.docx", "", ".pdf") == "report.pdf"
    with pytest.raises(ValueError, match="Unsupported"):
        names.output("photo.cr3", "", ".exe")
