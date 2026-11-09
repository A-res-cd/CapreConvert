from localraw.formats import CONVERSIONS, FORMATS


def test_picker_capabilities_use_normalized_formats_and_keep_existing_fields(api):
    client, _ = api
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    body = response.json()
    formats = {item["id"]: item for item in body["formats"]}
    assert set(formats) == {"jpg", "png", "webp", "cr3", "docx", "pdf", "odt"}
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
        ("odt", "docx"),
        ("docx", "odt"),
        ("odt", "pdf"),
        ("pdf", "odt"),
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


def test_all_odt_pairs_require_local_office_and_advertise_precise_previews(api, monkeypatch):
    from localraw import documents

    client, _ = api
    monkeypatch.setattr(documents, "libreoffice_executable", lambda configured=None: None)
    entries = {item["id"]: item for item in client.get("/api/v1/capabilities").json()["conversions"]}
    for conversion in ("odt_to_docx", "docx_to_odt", "odt_to_pdf", "pdf_to_odt"):
        entry = entries[conversion]
        assert not entry["available"] and "Install LibreOffice" in entry["setup_message"]
        assert entry["preview_kind"] == entry["target_format"]
        assert entry["settings_fields"] == [] and entry["direct_export"]
    assert entries["pdf_to_docx"]["available"]
    assert "no OCR" in entries["pdf_to_odt"]["limitations"][0]
    monkeypatch.setattr(documents, "libreoffice_executable", lambda configured=None: "local-office")
    entries = client.get("/api/v1/capabilities").json()["conversions"]
    assert all(item["available"] for item in entries)


def test_odt_upload_uses_document_limit_and_rejects_mismatched_format(api):
    from tests.support import upload

    client, app = api
    identifier = upload(client, name="letter.ODT", content=b"staged bytes are parsed only in workers")
    assert app.state.uploads.items[identifier]["state"] == "ready"
    too_large = client.post(
        "/api/v1/uploads",
        json={
            "filename": "large.odt",
            "size_bytes": app.state.settings.document_max_bytes + 1,
        },
    )
    assert too_large.status_code == 413
    mismatch = client.post(
        "/api/v1/jobs",
        json={
            "upload_ids": [identifier],
            "settings": {"conversion": "pdf_to_docx"},
        },
    )
    assert mismatch.status_code == 422
    assert (
        client.post("/api/v1/uploads", json={"filename": "unsafe.odf", "size_bytes": 4}).status_code
        == 422
    )
