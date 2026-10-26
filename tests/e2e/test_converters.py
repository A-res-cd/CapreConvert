"""Home/routing/export UI coverage; live_server uses explicitly named engine doubles."""

import re
import zipfile

import pytest
from PIL import Image
from playwright.sync_api import expect

from tests.e2e.test_browser import choose_converter


def open_home(page, app, url):
    page.goto(url + "/?launch=picker-test#bootstrap=" + app.state.security.bootstrap)
    expect(page.locator("#home-view")).to_be_visible()
    expect(page.locator("#pair-panel")).to_be_hidden()
    expect(page.locator("#versions")).to_contain_text("CapreConvert")
    assert "bootstrap" not in page.url


@pytest.mark.parametrize("width", [1440, 320])
def test_public_home_picker_local_assets_and_responsive_theme(browser, live_server, width):
    app, url = live_server
    context = browser.new_context(
        viewport={"width": width, "height": 1000}, reduced_motion="reduce", color_scheme="light"
    )
    page = context.new_page()
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    page.goto(url)
    expect(page).to_have_title("CapreConvert — Your files. Converted locally.")
    expect(page.locator("#home-title")).to_have_text("Your files. Converted locally.")
    expect(page.locator('meta[name="description"]')).to_have_attribute(
        "content", re.compile("CapreConvert.*documents.*CR3")
    )
    expect(
        page.get_by_text("Convert documents and RAW photos privately on your computer.", exact=True)
    ).to_be_visible()
    expect(page.get_by_role("heading", name="What do you want to convert?", exact=True)).to_be_visible()
    expect(page.locator(".conversion-card")).to_have_count(0)
    expect(page.locator("#pair-panel")).to_be_visible()
    expect(page.locator("#picker-input")).to_be_disabled()
    open_home(page, app, url)
    expect(page.locator("#picker-input optgroup")).to_have_count(2)
    expect(page.locator("#picker-output")).to_be_disabled()
    expect(page.locator("#converter-view")).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.get_by_role("button", name="Switch color theme", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.evaluate("document.fonts.ready")
    page.screenshot(path=f"test-results/capre-home-dark-{width}.png", full_page=True)
    page.get_by_role("button", name="Switch color theme", exact=True).click()
    page.screenshot(path=f"test-results/capre-home-light-{width}.png", full_page=True)
    assert requests and all(request.startswith(url + "/") for request in requests)
    assert not errors
    context.close()


def test_bootstrap_preserves_converter_route_and_native_back_forward(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url + "/#bootstrap=" + app.state.security.bootstrap + "&convert=cr3_to_png")
    expect(page.locator("#drop-zone")).to_be_enabled()
    expect(page.locator("#converter-title")).to_have_text("CR3 → PNG")
    assert "bootstrap" not in page.url and "convert=cr3_to_png" in page.url
    expect(page.locator("#jpeg-quality-settings")).to_be_hidden()
    page.get_by_role("link", name="CapreConvert home", exact=True).click()
    expect(page.locator("#home-view")).to_be_visible()
    choose_converter(page, "pdf", "docx")
    expect(page.locator("#converter-title")).to_have_text("PDF → DOCX")
    expect(page.locator("#converter-limitations")).to_contain_text("no OCR")
    expect(page.locator("#file-input")).to_have_attribute("accept", ".pdf")
    expect(page.locator("#raw-metadata-settings")).to_be_hidden()
    page.go_back()
    expect(page.locator("#home-view")).to_be_visible()
    page.go_back()
    expect(page.locator("#converter-title")).to_have_text("CR3 → PNG")
    expect(page.locator("#converter-view")).to_be_visible()
    page.reload()
    expect(page.locator("#converter-title")).to_have_text("CR3 → PNG")
    expect(page.locator("#drop-zone")).to_be_enabled()
    page.get_by_role("link", name="Skip to content", exact=True).focus()
    page.keyboard.press("Enter")
    expect(page.locator("#converter-view")).to_be_visible()
    expect(page.locator("#converter-title")).to_have_text("CR3 → PNG")
    page.goto(url + "/#convert=__proto__")
    expect(page.locator("#home-view")).to_be_visible()
    expect(page.locator("#versions")).to_contain_text("CapreConvert")
    assert not errors
    context.close()


def test_png_gallery_selected_exports_and_refresh(browser, live_server, tmp_path):
    app, url = live_server
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    open_home(page, app, url)
    choose_converter(page, "cr3", "png")
    page.locator("#file-input").set_input_files(
        [
            {"name": "one.cr3", "mimeType": "application/octet-stream", "buffer": b"good"},
            {"name": "two.cr3", "mimeType": "application/octet-stream", "buffer": b"good"},
        ]
    )
    page.locator("#start-button").click()
    expect(page.locator("#job-state")).to_have_text("Your PNGs are ready.", timeout=30000)
    expect(page.locator("#active-preview")).to_be_visible()
    expect(page.locator("#jpeg-quality-settings")).to_be_hidden()
    expect(page.locator("#preview-intro-copy")).to_contain_text("PNGs")
    page.get_by_role("checkbox", name="Export files/one.png as PNG", exact=True).check()
    page.reload()
    expect(page.get_by_role("checkbox", name="Export files/one.png as PNG", exact=True)).to_be_checked()
    with page.expect_download() as download:
        page.locator("#export-selected").click()
    assert download.value.suggested_filename == "one.png"
    path = tmp_path / "one.png"
    download.value.save_as(path)
    with Image.open(path) as image:
        assert image.format == "PNG" and image.size == (8, 6)
    page.locator("#select-all-previews").click()
    with page.expect_download() as download:
        page.locator("#export-selected").click()
    selected = tmp_path / "selected.zip"
    download.value.save_as(selected)
    with zipfile.ZipFile(selected) as archive:
        assert archive.namelist() == ["files/one.png", "files/two.png"]
        assert archive.testzip() is None
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path="test-results/capre-png-workspace.png", full_page=True)
    job = next(iter(app.state.jobs.items.values()))
    assert job["settings"]["conversion"] == "cr3_to_png"
    context.close()


@pytest.mark.parametrize(
    "conversion,source,ready,output",
    [
        ("docx_to_pdf", "source.docx", "Your PDFs are ready.", "source.pdf"),
        ("pdf_to_docx", "source.pdf", "Your Word documents are ready.", "source.docx"),
    ],
)
def test_document_workspace_download_and_restore_using_ui_worker_double(
    browser, live_server, monkeypatch, tmp_path, conversion, source, ready, output
):
    from localraw import documents

    # Only browser wiring is under test; no fake executable is launched.
    monkeypatch.setattr(documents, "libreoffice_executable", lambda configured=None: "UI-engine-double")
    app, url = live_server
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    open_home(page, app, url)
    choose_converter(
        page,
        "docx" if conversion == "docx_to_pdf" else "pdf",
        "pdf" if conversion == "docx_to_pdf" else "docx",
    )
    expect(page.locator("#jpeg-quality-settings")).to_be_hidden()
    expect(page.locator("#white-balance-setting")).to_be_hidden()
    expect(page.locator("#raw-metadata-settings")).to_be_hidden()
    page.locator("#file-input").set_input_files(
        {"name": source, "mimeType": "application/octet-stream", "buffer": b"explicit-ui-worker-fixture"}
    )
    page.locator("#start-button").click()
    expect(page.locator("#job-state")).to_have_text(ready, timeout=25000)
    expect(page.locator("#preview-section")).to_be_visible()
    expect(page.locator("#review-previews")).to_be_visible()
    if conversion == "docx_to_pdf":
        expect(page.locator("#active-preview")).to_be_visible(timeout=15000)
        expect(page.locator("#pdf-page-status")).to_have_text("Page 1 of 2")
        page.locator("#pdf-next").click()
        expect(page.locator("#pdf-page-status")).to_have_text("Page 2 of 2")
        expect(page.locator("#pdf-next")).to_be_disabled()
        page.locator("#pdf-previous").click()
        expect(page.locator("#pdf-page-status")).to_have_text("Page 1 of 2")
    else:
        expect(page.locator("#docx-content")).to_contain_text("Explicit UI worker double", timeout=15000)
        expect(page.locator("#docx-content")).to_contain_text("not exact Word page layout")
    with page.expect_download() as primary:
        page.locator("#download-primary").click()
    assert primary.value.suggested_filename == output
    expect(page.locator("#result-files")).not_to_contain_text("undefined")
    with page.expect_download() as download:
        page.get_by_role("link", name="Download files/" + output, exact=True).click()
    path = tmp_path / output
    download.value.save_as(path)
    if output.endswith(".pdf"):
        from pypdf import PdfReader

        assert len(PdfReader(path).pages) == 2
    else:
        from docx import Document

        assert "Explicit UI worker double" in Document(path).paragraphs[0].text
    assert next(iter(app.state.jobs.items.values()))["settings"]["conversion"] == conversion
    page.reload()
    expect(page.locator("#job-state")).to_have_text(ready)
    expect(page.locator("#converter-title")).to_have_text(
        "DOCX → PDF" if conversion == "docx_to_pdf" else "PDF → DOCX"
    )
    page.evaluate("window.scrollTo(0, 0)")
    page.screenshot(path=f"test-results/capre-{conversion}-workspace.png", full_page=True)
    context.close()


def test_docx_pdf_missing_local_engine_is_honest_and_does_not_upload(browser, live_server, monkeypatch):
    from localraw import documents

    monkeypatch.setattr(documents, "libreoffice_executable", lambda configured=None: None)
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    open_home(page, app, url)
    page.locator("#picker-input").select_option("docx")
    expect(page.locator("#picker-output")).to_have_value("pdf")
    expect(page.locator("#picker-status")).to_contain_text("Install LibreOffice")
    expect(page.locator("#open-converter")).to_be_disabled()
    page.goto(url + "/#convert=docx_to_pdf")
    expect(page.locator("#converter-availability")).to_contain_text("Install LibreOffice")
    expect(page.locator("#drop-zone")).to_be_disabled()
    expect(page.locator("#start-button")).to_be_disabled()
    assert not app.state.uploads.items
    context.close()
