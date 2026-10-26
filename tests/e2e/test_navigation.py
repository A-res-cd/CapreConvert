from playwright.sync_api import expect

from tests.e2e.test_browser import connect


def test_desktop_navigation_collapses_restores_and_supports_both_themes(browser, live_server):
    app, url = live_server
    context = browser.new_context(viewport={"width": 1440, "height": 1050}, color_scheme="light")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    connect(page, app, url)
    toggle = page.get_by_role("button", name="Toggle workspace navigation", exact=True)
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expanded_x = page.locator("#main").bounding_box()["x"]
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(page.locator("html")).to_have_attribute("data-navigation", "collapsed")
    page.reload()
    expect(page.locator("#drop-zone")).to_be_enabled()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    assert page.locator("#main").bounding_box()["x"] < expanded_x
    page.get_by_role("link", name="Output settings", exact=True).click()
    expect(page.locator("#settings-title")).to_be_in_viewport()
    expect(page.locator("#preview-navigation-link")).to_have_attribute("aria-disabled", "true")
    toggle.click()
    page.evaluate("window.scrollTo(0, 0)")
    page.evaluate("document.fonts.ready")
    assert page.evaluate("document.fonts.check('600 32px Fraunces')")
    page.screenshot(path="test-results/style-light.png", animations="disabled")
    page.get_by_role("button", name="Switch color theme").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.screenshot(path="test-results/style-dark.png", animations="disabled")
    assert not errors
    context.close()


def test_mobile_navigation_drawer_escape_and_section_links(browser, live_server):
    app, url = live_server
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, reduced_motion="reduce"
    )
    page = context.new_page()
    connect(page, app, url)
    toggle = page.get_by_role("button", name="Toggle workspace navigation", exact=True)
    expect(toggle).to_have_attribute("aria-expanded", "false")
    assert page.locator("#workspace-navigation").evaluate("element => element.inert")
    toggle.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(page.get_by_role("link", name="Convert files", exact=True)).to_be_focused()
    assert page.locator("#main").evaluate("element => element.inert")
    page.screenshot(path="test-results/style-mobile-navigation.png", animations="disabled")
    page.keyboard.press("Escape")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_be_focused()
    assert not page.locator("#main").evaluate("element => element.inert")
    toggle.click()
    page.get_by_role("link", name="Output settings", exact=True).click()
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(page.locator("#settings-title")).to_be_in_viewport()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    context.close()
