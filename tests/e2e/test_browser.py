import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def choose_converter(page, source, target):
    page.get_by_label("Input file type", exact=True).select_option(source)
    page.get_by_label("Output file type", exact=True).select_option(target)
    page.get_by_role("button", name="Open converter", exact=True).click()


def connect(page, app, url):
    page.goto(url + "/#bootstrap=" + app.state.security.bootstrap)
    expect(page.locator("#home-view")).to_be_visible()
    choose_converter(page, "cr3", "jpg")
    expect(page.locator("#drop-zone")).to_be_enabled()
    assert "bootstrap" not in page.url


def test_conversion_partial_success_download_refresh_and_local_requests(browser, live_server, tmp_path):
    app, url = live_server
    context = browser.new_context(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    requests, errors = [], []
    page.on("request", lambda request: requests.append(request.url))
    page.on("pageerror", lambda error: errors.append(str(error)))
    context.route(
        "**/*",
        lambda route: route.continue_() if route.request.url.startswith(url + "/") else route.abort(),
    )
    connect(page, app, url)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("nested/scene.CR3", b"good")
    with page.expect_file_chooser() as chooser:
        page.get_by_role("button", name="Choose CR3 photos or ZIP archives").click()
    chooser.value.set_files(
        [
            {"name": "photo.CR3", "mimeType": "application/octet-stream", "buffer": b"good"},
            {"name": "broken.CR3", "mimeType": "application/octet-stream", "buffer": b"bad"},
            {"name": "trip.zip", "mimeType": "application/zip", "buffer": buffer.getvalue()},
        ]
    )
    page.get_by_label("JPEG quality").evaluate(
        "el => {el.value = '91'; el.dispatchEvent(new Event('input', {bubbles:true}));}"
    )
    page.get_by_label("White balance").select_option("auto")
    page.get_by_label("Filename suffix").fill("_web")
    page.get_by_label("Keep photo metadata").uncheck()
    page.get_by_label("Process at once").select_option("2")
    expect(page.locator("#quality-value")).to_have_text("91")
    page.get_by_role("button", name="Convert 3 inputs to JPEG").click()
    expect(page.locator("#job-state")).to_have_text("Ready, with a few exceptions.", timeout=25000)
    expect(page.locator("#job-detail")).to_contain_text("2 ready · 1 failed")
    expect(page.locator("#result-files")).to_contain_text("Deterministic invalid-image double.")
    job = next(iter(app.state.jobs.items.values()))
    assert job["settings"]["jpeg_quality"] == 91 and job["settings"]["white_balance"] == "auto"
    with page.expect_download() as download:
        page.get_by_role("link", name="Download files/photo_web.jpg", exact=True).click()
    jpeg = tmp_path / "result.jpg"
    download.value.save_as(jpeg)
    with Image.open(jpeg) as result:
        assert result.size == (8, 6)
    with page.expect_download() as download:
        page.locator("#download-all").click()
    archive_path = tmp_path / "result.zip"
    download.value.save_as(archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == ["files/photo_web.jpg", "trip/nested/scene_web.jpg"]
    page.reload()
    expect(page.locator("#job-state")).to_have_text("Ready, with a few exceptions.")
    expect(page.locator("#job-expiry")).to_contain_text("Available until")
    page.screenshot(path="test-results/desktop-results.png", full_page=True)
    assert requests and all(request.startswith(url) for request in requests)
    assert not errors
    context.close()


def test_cancel_keeps_successes_and_explicit_retry(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    connect(page, app, url)
    page.locator("#file-input").set_input_files(
        [
            {"name": "done.cr3", "mimeType": "application/octet-stream", "buffer": b"good"},
            {"name": "slow.cr3", "mimeType": "application/octet-stream", "buffer": b"hang"},
        ]
    )
    page.locator("#start-button").click()
    expect(page.get_by_role("link", name="Download files/done.jpg", exact=True)).to_be_visible(
        timeout=20000
    )
    page.locator("#cancel-button").click()
    expect(page.locator("#job-state")).to_have_text("Batch cancelled.", timeout=10000)
    expect(page.get_by_role("link", name="Download files/done.jpg", exact=True)).to_be_visible()
    expect(page.locator("#download-all")).to_be_visible()
    page.locator("#retry-button").click()
    expect(page.locator("#job-state")).to_have_text("Developing your photos", timeout=10000)
    page.locator("#cancel-button").click()
    expect(page.locator("#job-state")).to_have_text("Batch cancelled.", timeout=10000)
    context.close()


@pytest.mark.parametrize("width", [320, 390])
def test_mobile_pairing_keyboard_theme_and_layout(browser, live_server, width):
    app, url = live_server
    context = browser.new_context(
        viewport={"width": width, "height": 844}, is_mobile=True, has_touch=True, reduced_motion="reduce"
    )
    page = context.new_page()
    page.goto(url)
    expect(page.locator("#pair-panel")).to_be_visible()
    page.get_by_label("Pairing code", exact=True).fill(app.state.security.pairing)
    page.get_by_role("button", name="Connect browser").click()
    choose_converter(page, "cr3", "jpg")
    expect(page.locator("#drop-zone")).to_be_enabled()
    page.locator("#drop-zone").focus()
    with page.expect_file_chooser() as chooser:
        page.keyboard.press("Enter")
    chooser.value.set_files(
        {"name": "sample.CR3", "mimeType": "application/octet-stream", "buffer": b"good"}
    )
    expect(page.locator("#start-button")).to_be_enabled()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for selector in ("#start-button", "#drop-zone", "#theme-toggle"):
        box = page.locator(selector).bounding_box()
        assert box["height"] >= 44 and box["width"] >= 44
    page.get_by_role("button", name="Switch color theme").click()
    theme = page.locator("html").get_attribute("data-theme")
    page.reload()
    expect(page.locator("#drop-zone")).to_be_enabled()
    assert page.locator("html").get_attribute("data-theme") == theme
    Path("test-results").mkdir(exist_ok=True)
    page.screenshot(path=f"test-results/mobile-{width}.png", full_page=True)
    context.close()


def test_duplicate_names_and_preflight_validation(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    connect(page, app, url)
    registrations = []
    page.on(
        "request",
        lambda request: (
            registrations.append(request.url)
            if request.method == "POST" and request.url.endswith("/uploads")
            else None
        ),
    )
    page.locator("#file-input").set_input_files(
        [
            {"name": "same.cr3", "mimeType": "application/octet-stream", "buffer": b"good"},
            {"name": "same.cr3", "mimeType": "application/octet-stream", "buffer": b"also"},
        ]
    )
    expect(page.locator("#selection-count")).to_contain_text("2 selected")
    page.get_by_label("Filename suffix").fill("/invalid")
    page.locator("#start-button").click()
    expect(page.locator("#notice")).to_contain_text("Suffix can contain")
    assert not registrations
    page.get_by_label("Filename suffix").fill("")
    page.locator("#start-button").click()
    expect(page.locator("#job-state")).to_have_text("Your JPEGs are ready.", timeout=20000)
    expect(page.get_by_role("link", name="Download files/same.jpg", exact=True)).to_be_visible()
    expect(page.get_by_role("link", name="Download files/same__2.jpg", exact=True)).to_be_visible()
    assert len(registrations) == 2
    context.close()


def test_refresh_restores_job_beyond_first_history_page(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    connect(page, app, url)
    app.state.jobs.close()  # Deterministic queued jobs, no image worker is needed for this check.
    csrf = page.request.get(url + "/api/v1/sessions").json()["csrf_token"]
    headers = {"Origin": url, "X-CSRF-Token": csrf}
    registered = page.request.post(
        url + "/api/v1/uploads", data={"filename": "retained.cr3", "size_bytes": 4}, headers=headers
    )
    upload_id = registered.json()["upload_id"]
    assert (
        page.request.put(
            url + f"/api/v1/uploads/{upload_id}/content", data=b"good", headers=headers
        ).status
        == 200
    )
    ids = []
    for _ in range(27):
        response = page.request.post(
            url + "/api/v1/jobs", data={"upload_ids": [upload_id]}, headers=headers
        )
        assert response.status == 202
        identifier = response.json()["id"]
        ids.append(identifier)
        assert (
            page.request.post(url + f"/api/v1/jobs/{identifier}/cancel", headers=headers).status == 200
        )
    page.locator("#refresh-history").click()
    expect(page.locator(".history-item")).to_have_count(25)
    page.locator("#more-history").click()
    expect(page.locator(".history-item")).to_have_count(27)
    page.locator(".history-item").last.click()
    expect(page.locator("#job-label")).to_have_text("BATCH " + ids[0][:8].upper())
    page.reload()
    expect(page.locator("#job-label")).to_have_text("BATCH " + ids[0][:8].upper())
    context.close()
