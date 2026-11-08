"""Headless check of the landing view, links and dialog; saves screenshots to docs/."""

import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE, wait_until="networkidle")
    page.evaluate("localStorage.clear()")
    page.reload(wait_until="networkidle")
    page.wait_for_timeout(1800)
    page.screenshot(path="docs/01-home.png")

    page.click("#openHow")
    page.wait_for_timeout(500)
    page.screenshot(path="docs/05-how-it-works.png")
    page.click(".how .close")

    results = []
    for link in page.locator("a[target=_blank]").all():
        href, text = link.get_attribute("href"), link.inner_text()
        with ctx.expect_page() as info:
            link.click()
        tab = info.value
        tab.wait_for_load_state("domcontentloaded")
        resp_ok = tab.evaluate("document.title")
        slug = text.lower().replace(" ", "-")
        tab.wait_for_timeout(1500)
        tab.screenshot(path=f"docs/link-{slug}.png")
        results.append((text, href, tab.url, resp_ok))
        tab.close()
    for r in results:
        print("LINK", *r, sep=" | ")
    print("console errors:", errors)
    browser.close()
