from localraw.formats import CONVERSIONS, FORMATS


def test_picker_capabilities_use_normalized_formats_and_keep_existing_fields(api):
    client, _ = api
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    body = response.json()
    formats = {item["id"]: item for item in body["formats"]}
    assert set(formats) == {"jpg", "png", "webp", "cr3", "docx", "pdf"}
    assert "zip" not in formats and "jpeg" not in formats
    assert formats["cr3"]["category"] == "images"
    expected = {
        ("jpg", "jpg"),
        ("jpg", "png"),
        ("jpg", "webp"),
        ("png", "jpg"),
        ("png", "png"),
        ("png", "webp"),
        ("webp", "jpg"),
        ("webp", "png"),
        ("webp", "webp"),
        ("cr3", "jpg"),
        ("cr3", "png"),
        ("docx", "pdf"),
        ("pdf", "docx"),
    }
    assert {(item["source_format"], item["target_format"]) for item in body["conversions"]} == expected
    assert len(body["conversions"]) == len(CONVERSIONS)
    for item in body["conversions"]:
        assert item["source_format"] in FORMATS and item["target_format"] in FORMATS
        for key in (
            "input_extensions",
            "output_extension",
            "media_type",
            "is_raw",
            "engine",
            "available",
            "archive_input",
            "preview_kind",
            "direct_export",
        ):
            assert key in item
    assert (
        ".zip"
        in next(item for item in body["conversions"] if item["id"] == "cr3_to_jpg")["input_extensions"]
    )
