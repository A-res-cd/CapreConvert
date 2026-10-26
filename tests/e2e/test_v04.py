import io

import pytest
from PIL import Image
from playwright.sync_api import expect

from tests.e2e.test_browser import choose_converter
from tests.e2e.test_converters import open_home


@pytest.mark.parametrize("width", [1440, 320])
def test_real_raster_controls_alpha_direct_zip_refresh(browser, live_server, tmp_path, width):
    app, url = live_server
    context = browser.new_context(viewport={"width": width, "height": 950}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    open_home(page, app, url)
    choose_converter(page, "png", "webp")
    expect(page.locator("#raster-settings")).to_be_visible()
    expect(page.locator("#metadata-hint")).to_have_text(
        "Supported capture fields only. Other tags are omitted."
    )
    expect(page.locator("#raster-background-setting")).to_be_hidden()
    expect(page.locator("#white-balance-setting")).to_be_hidden()
    page.locator("#max-width").fill("30")
    page.locator("#raster-settings summary").click()
    page.locator("#webp-lossless").check()
    buffer = io.BytesIO()
    with Image.new("RGBA", (60, 40), (20, 70, 120, 40)) as image:
        image.save(buffer, format="PNG")
    page.locator("#file-input").set_input_files(
        [
            {"name": name, "mimeType": "image/png", "buffer": buffer.getvalue()}
            for name in ("one.png", "two.png")
        ]
    )
    page.locator("#start-button").click()
    expect(page.locator("#job-state")).to_have_text("Your WEBP images are ready.", timeout=30000)
    expect(page.locator("#active-preview")).to_be_visible()
    expect(page.locator("#preview-dimensions")).to_contain_text("30 × 20")
    expect(page.locator("#result-files")).to_contain_text("input")
    page.get_by_role("checkbox", name="Export files/one.webp as WEBP", exact=True).check()
    page.reload()
    expect(
        page.get_by_role("checkbox", name="Export files/one.webp as WEBP", exact=True)
    ).to_be_checked()
    with page.expect_download() as download:
        page.locator("#export-selected").click()
    assert download.value.suggested_filename == "one.webp"
    target = tmp_path / "one.webp"
    download.value.save_as(target)
    with Image.open(target) as image:
        assert image.mode == "RGBA" and image.size == (30, 20)
    page.locator("#select-all-previews").click()
    with page.expect_download() as download:
        page.locator("#export-selected").click()
    assert download.value.suggested_filename.endswith(".zip")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.screenshot(path=f"test-results/v04-raster-{width}.png", full_page=True)
    assert not errors
    context.close()
