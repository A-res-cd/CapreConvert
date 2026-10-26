"""Capability picker behavior, state isolation, explicit routes and native controls."""

import json

from playwright.sync_api import expect

from tests.e2e.test_browser import choose_converter
from tests.e2e.test_converters import open_home


def values(page, element):
    return page.locator(element + " option").evaluate_all(
        "options => options.map(option => option.value).filter(Boolean)"
    )


def test_groups_filter_aliases_retention_and_single_target(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    open_home(page, app, url)
    expect(page.locator("#picker-input")).to_have_value("")
    expect(page.locator("#picker-output")).to_be_disabled()
    expect(page.locator("#open-converter")).to_be_disabled()
    assert set(values(page, "#picker-input")) == {"jpg", "png", "webp", "cr3", "docx", "pdf"}
    assert page.locator("#picker-input optgroup").evaluate_all("groups => groups.map(g => g.label)") == [
        "Images",
        "Documents",
    ]
    assert page.locator("#picker-input option[value=jpg]").count() == 1
    assert "zip" not in values(page, "#picker-input")
    for source, outputs in [
        ("jpg", {"jpg", "png", "webp"}),
        ("png", {"jpg", "png", "webp"}),
        ("webp", {"jpg", "png", "webp"}),
        ("cr3", {"jpg", "png"}),
        ("pdf", {"docx"}),
        ("docx", {"pdf"}),
    ]:
        page.locator("#picker-input").select_option(source)
        assert set(values(page, "#picker-output")) == outputs
    page.locator("#picker-input").select_option("jpg")
    page.locator("#picker-output").select_option("webp")
    page.locator("#picker-input").select_option("png")
    expect(page.locator("#picker-output")).to_have_value("webp")
    page.locator("#picker-input").select_option("cr3")
    expect(page.locator("#picker-output")).to_have_value("")
    page.locator("#picker-input").select_option("pdf")
    expect(page.locator("#picker-output")).to_have_value("docx")
    page.locator("#picker-input").select_option("png")
    page.locator("#picker-output").select_option("png")
    expect(page.locator("#picker-status")).to_have_text("Optimize size, quality or dimensions.")
    expect(page.locator("#home-view")).to_be_visible()
    page.locator("#open-converter").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#converter-title")).to_have_text("PNG → PNG")
    context.close()


def test_pending_picker_never_mutates_files_job_settings_and_deep_link_sync(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    open_home(page, app, url)
    choose_converter(page, "cr3", "jpg")
    page.locator("#file-input").set_input_files(
        {"name": "queued.cr3", "mimeType": "application/octet-stream", "buffer": b"good"}
    )
    page.locator("#quality").fill("92")
    page.get_by_role("link", name="CapreConvert home", exact=True).click()
    expect(page.locator("#picker-input")).to_have_value("cr3")
    page.locator("#picker-input").select_option("png")
    page.locator("#picker-output").select_option("webp")
    assert page.locator("#selected-files").text_content().find("queued.cr3") >= 0
    expect(page.locator("#quality")).to_have_value("92")
    assert not app.state.jobs.items
    page.go_back()
    expect(page.locator("#converter-title")).to_have_text("CR3 → JPG")
    expect(page.locator("#selection-count")).to_contain_text("1 selected")
    page.locator("#start-button").click()
    expect(page.locator("#job-state")).to_have_text("Your JPEGs are ready.", timeout=20000)
    job = next(iter(app.state.jobs.items.values()))
    original = json.dumps(job["settings"], sort_keys=True)
    page.get_by_role("link", name="CapreConvert home", exact=True).click()
    page.locator("#picker-input").select_option("pdf")
    assert json.dumps(job["settings"], sort_keys=True) == original
    page.goto(url + "/#convert=png_to_webp")
    expect(page.locator("#converter-title")).to_have_text("PNG → WEBP")
    page.get_by_role("link", name="CapreConvert home", exact=True).click()
    expect(page.locator("#picker-input")).to_have_value("png")
    expect(page.locator("#picker-output")).to_have_value("webp")
    page.goto(url + "/#convert=unknown_converter")
    expect(page.locator("#home-view")).to_be_visible()
    expect(page.locator("#notice")).to_contain_text("Unknown or unsupported")
    context.close()


def test_loading_failure_retry_and_no_fallback_choices(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()
    pending = []
    page.route("**/api/v1/capabilities", lambda route: pending.append(route))
    page.goto(url + "/#bootstrap=" + app.state.security.bootstrap)
    expect(page.locator("#picker-status")).to_have_text("Loading supported conversions…")
    expect(page.locator("#picker-input")).to_be_disabled()
    expect(page.locator("#open-converter")).to_be_disabled()
    page.wait_for_timeout(100)
    assert pending
    pending[0].fulfill(
        status=503,
        content_type="application/json",
        body=json.dumps({"error": {"message": "Test capability outage"}}),
    )
    expect(page.locator("#picker-status")).to_contain_text("could not load")
    assert not values(page, "#picker-input")
    page.unroute("**/api/v1/capabilities")
    page.locator("#picker-retry").click()
    expect(page.locator("#picker-input")).to_be_enabled()
    expect(page.locator("#picker-input")).to_be_focused()
    context.close()


def test_duplicate_engines_and_empty_registry_are_explicit(browser, live_server):
    app, url = live_server
    context = browser.new_context()
    page = context.new_page()

    def duplicate(route):
        response = route.fetch()
        caps = response.json()
        first = next(item for item in caps["conversions"] if item["id"] == "png_to_webp")
        caps["conversions"].append({**first, "id": "alternate_engine"})
        route.fulfill(response=response, json=caps)

    page.route("**/api/v1/capabilities", duplicate)
    open_home(page, app, url)
    page.locator("#picker-input").select_option("png")
    page.locator("#picker-output").select_option("webp")
    expect(page.locator("#open-converter")).to_be_disabled()
    expect(page.locator("#picker-status")).to_contain_text("Multiple engines")
    page.unroute("**/api/v1/capabilities")

    def empty(route):
        response = route.fetch()
        caps = response.json()
        caps["conversions"] = []
        route.fulfill(response=response, json=caps)

    page.route("**/api/v1/capabilities", empty)
    page.reload()
    expect(page.locator("#picker-status")).to_contain_text("No supported conversions")
    expect(page.locator("#open-converter")).to_be_disabled()
    context.close()


def test_picker_mobile_layout_keyboard_and_sidebar(browser, live_server):
    app, url = live_server
    context = browser.new_context(viewport={"width": 320, "height": 900}, reduced_motion="reduce")
    page = context.new_page()
    open_home(page, app, url)
    input_box = page.locator("#picker-input").bounding_box()
    output_box = page.locator("#picker-output").bounding_box()
    assert output_box["y"] > input_box["y"] and input_box["height"] >= 44
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.locator("#picker-input").select_option("png")
    page.locator("#picker-output").select_option("webp")
    page.locator("#open-converter").focus()
    page.keyboard.press("Enter")
    expect(page.locator("#converter-title")).to_be_focused()
    expect(page.locator("#current-section-label")).to_have_text("PNG → WEBP")
    page.locator("#navigation-toggle").click()
    expect(page.get_by_role("link", name="Convert files", exact=True)).to_have_attribute(
        "aria-current", "location"
    )
    assert page.locator("#workspace-navigation a[data-conversion]").count() == 0
    page.keyboard.press("Escape")
    expect(page.locator("#navigation-toggle")).to_be_focused()
    page.get_by_role("link", name="CapreConvert home", exact=True).click()
    page.screenshot(path="test-results/v1-picker-mobile.png", full_page=True)
    context.close()
