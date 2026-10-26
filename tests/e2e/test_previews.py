import copy
import shutil
import zipfile

from PIL import Image
from playwright.sync_api import expect

from localraw.storage import opaque_id
from tests.e2e.test_browser import choose_converter, connect


def prepare(page, files):
    page.locator("#file-input").set_input_files(
        [
            {"name": name, "mimeType": "application/octet-stream", "buffer": contents}
            for name, contents in files
        ]
    )
    page.get_by_label("Process at once").select_option("2")
    page.locator("#start-button").click()
    expect(page.locator("#job-state")).to_have_text(
        "Ready, with a few exceptions."
        if any(data == b"bad" for _, data in files)
        else "Your JPEGs are ready.",
        timeout=45000,
    )
    expect(page.locator("#active-preview")).to_be_visible()


def test_preview_selection_refresh_and_single_or_multiple_exports(browser, live_server, tmp_path):
    app, url = live_server
    context = browser.new_context(viewport={"width": 1280, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    connect(page, app, url)
    prepare(
        page,
        [("one.cr3", b"good"), ("two.cr3", b"good"), ("three.cr3", b"good"), ("failed.cr3", b"bad")],
    )
    expect(page.get_by_role("heading", name="Output preview")).to_be_visible()
    expect(page.locator(".preview-tile")).to_have_count(3)
    expect(page.locator("#export-selection-count")).to_have_text("0 of 3 results selected")
    expect(page.locator("#export-selected")).to_be_disabled()
    page.get_by_role("button", name="Preview files/two.jpg", exact=True).click()
    expect(page.locator("#preview-filename")).to_have_text("files/two.jpg")
    expect(page.locator("#preview-position")).to_have_text("Result 2 of 3")
    page.get_by_role("checkbox", name="Export files/one.jpg as JPG", exact=True).check()
    page.get_by_role("checkbox", name="Export files/three.jpg as JPG", exact=True).check()
    page.get_by_label("Include viewed result in export").check()
    expect(page.locator("#export-selection-count")).to_have_text("3 of 3 results selected")
    page.get_by_label("Include viewed result in export").uncheck()
    page.reload()
    expect(page.locator("#export-selection-count")).to_have_text("2 of 3 results selected")
    expect(page.locator("#preview-filename")).to_have_text("files/two.jpg")
    expect(page.get_by_role("checkbox", name="Export files/one.jpg as JPG", exact=True)).to_be_checked()
    expect(
        page.get_by_role("checkbox", name="Export files/two.jpg as JPG", exact=True)
    ).not_to_be_checked()
    with page.expect_download() as download:
        page.locator("#export-selected").click()
    selected = tmp_path / "selected.zip"
    download.value.save_as(selected)
    with zipfile.ZipFile(selected) as archive:
        assert archive.namelist() == ["files/one.jpg", "files/three.jpg"]
        assert archive.testzip() is None
    page.locator("#clear-preview-selection").click()
    expect(page.locator("#export-selected")).to_be_disabled()
    page.locator("#select-all-previews").click()
    expect(page.locator("#export-selection-count")).to_have_text("3 of 3 results selected")
    page.locator("#clear-preview-selection").click()
    page.get_by_role("checkbox", name="Export files/two.jpg as JPG", exact=True).check()
    with page.expect_download() as download:
        page.locator("#export-selected").click()
    assert download.value.suggested_filename == "two.jpg"
    photo = tmp_path / "two.jpg"
    download.value.save_as(photo)
    job = next(iter(app.state.jobs.items.values()))
    original = next(file for file in job["files"] if file["output_name"] == "files/two.jpg")
    assert photo.read_bytes() == app.state.jobs.output_path(job, original).read_bytes()
    page.locator("#next-preview").click()
    expect(page.locator("#preview-position")).to_have_text("Result 3 of 3")
    page.screenshot(path="test-results/preview-desktop.png", full_page=True)
    assert not errors
    context.close()


def test_preview_mobile_keyboard_and_no_horizontal_overflow(browser, live_server):
    app, url = live_server
    context = browser.new_context(viewport={"width": 320, "height": 844}, is_mobile=True, has_touch=True)
    page = context.new_page()
    connect(page, app, url)
    filename = "long-camera-shot-" + "sample-" * 12 + ".cr3"
    prepare(page, [(filename, b"good")])
    checkbox = page.get_by_role("checkbox", name=f"Export files/{filename[:-4]}.jpg as JPG", exact=True)
    checkbox.focus()
    page.keyboard.press("Space")
    expect(page.locator("#export-selection-count")).to_have_text("1 of 1 results selected")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for selector in (
        "#export-selected",
        "#select-all-previews",
        "#clear-preview-selection",
        "#previous-preview",
        "#next-preview",
    ):
        box = page.locator(selector).bounding_box()
        assert box["width"] >= 44 and box["height"] >= 44
    assert page.locator("#active-preview").evaluate("image => image.naturalWidth > 0")
    page.screenshot(path="test-results/preview-mobile.png", full_page=True)
    context.close()


def test_gallery_pagination_keeps_selection_across_pages(browser, live_server, tmp_path):
    app, url = live_server
    context = browser.new_context(accept_downloads=True)
    page = context.new_page()
    connect(page, app, url)
    prepare(page, [("source.cr3", b"good")])
    # Expand the deterministic fixture batch without invoking 14 image processes.
    with app.state.workspace.lock:
        jobs = app.state.jobs
        job = next(iter(jobs.items.values()))
        original = job["files"][0]
        copies = []
        for index in range(14):
            file = copy.deepcopy(original)
            file["id"], file["output_id"] = opaque_id(), opaque_id()
            file["name"], file["output_name"] = (
                f"shot{index + 1:02}.cr3",
                f"files/shot{index + 1:02}.jpg",
            )
            shutil.copyfile(jobs.output_path(job, original), jobs.output_path(job, file))
            for thumbnail in (False, True):
                shutil.copyfile(
                    jobs.preview_path(job, original, thumbnail), jobs.preview_path(job, file, thumbnail)
                )
            copies.append(file)
        job["files"] = copies
        jobs.save(job)
    page.reload()
    expect(page.locator(".preview-tile")).to_have_count(12)
    page.get_by_role("checkbox", name="Export files/shot01.jpg as JPG", exact=True).check()
    page.locator("#next-preview-page").click()
    expect(page.locator(".preview-tile")).to_have_count(2)
    page.get_by_role("checkbox", name="Export files/shot13.jpg as JPG", exact=True).check()
    expect(page.locator("#export-selection-count")).to_have_text("2 of 14 results selected")
    page.reload()
    expect(page.locator("#preview-page")).to_have_text("2 / 2")
    expect(
        page.get_by_role("checkbox", name="Export files/shot13.jpg as JPG", exact=True)
    ).to_be_checked()
    with page.expect_download() as download:
        page.locator("#export-selected").click()
    path = tmp_path / "across-pages.zip"
    download.value.save_as(path)
    with zipfile.ZipFile(path) as archive:
        assert archive.namelist() == ["files/shot01.jpg", "files/shot13.jpg"]
        with Image.open(archive.open("files/shot13.jpg")) as image:
            assert image.size == (8, 6)
    context.close()


def test_launch_link_preserves_existing_session_and_export_choices(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    connect(page, app, url)
    prepare(page, [("retained.cr3", b"good")])
    page.get_by_role("checkbox", name="Export files/retained.jpg as JPG", exact=True).check()
    original_label = page.locator("#job-label").inner_text()
    original_sessions = len(app.state.security.sessions)
    # A fresh launcher link supplies a new bootstrap; an existing valid cookie wins.
    app.state.security.bootstrap = "fresh-launch-bootstrap-fixture"
    page.goto(url + "/?launch=restart#bootstrap=" + app.state.security.bootstrap)
    choose_converter(page, "cr3", "jpg")
    expect(page.locator("#drop-zone")).to_be_enabled()
    expect(page.locator("#job-label")).to_have_text(original_label)
    expect(page.locator("#export-selection-count")).to_have_text("1 of 1 results selected")
    assert len(app.state.security.sessions) == original_sessions
    assert "bootstrap" not in page.url
    context.close()
