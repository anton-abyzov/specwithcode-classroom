"""Headless walkthrough of the demo script; saves screenshots to docs/."""

import sys
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"


def wait_reply(page, n):
    page.wait_for_function(f"document.querySelectorAll('.msg.bot .who-said, .msg.bot .error').length >= {n}", timeout=240_000)


with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page.goto(BASE)
    page.evaluate("localStorage.clear()")
    page.reload()
    page.click("#resetRing")
    page.wait_for_selector(".provider")
    page.screenshot(path="docs/01-home.png")

    page.locator(".provider", has_text="OpenAI").locator(".toggle").click()
    page.click("text=Physics: projectile")
    wait_reply(page, 1)
    page.locator(".msg.bot .who-said").last.scroll_into_view_if_needed()
    page.evaluate("document.querySelector('#feed').scrollTop = document.querySelector('.msg.bot').offsetTop - 120")
    page.wait_for_timeout(800)
    page.screenshot(path="docs/02-failover-physics.png")

    page.locator(".provider", has_text="OpenAI").locator(".toggle").click()
    page.fill("#input", "Make a 6-slide presentation for science class on how volcanoes form, with speaker notes.")
    page.click("#send")
    wait_reply(page, 2)
    page.locator(".artifact").last.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    page.screenshot(path="docs/03-slides.png")

    page.fill("#input", "Build a mobile app for our class book club: list of books, a reading-minutes tracker per day saved on the phone, and a progress ring.")
    page.click("#send")
    wait_reply(page, 3)
    page.locator(".phone").last.scroll_into_view_if_needed()
    page.wait_for_timeout(2500)
    page.screenshot(path="docs/04-app.png")
    errors = page.locator(".msg.bot .error").count()
    print("errors:", errors)
    browser.close()
