"""
Patchright browser singleton. All bot tasks share one browser page.

Uses a persistent profile so Cloudflare trusts the session over time.
"""

import json
import os
import paths
from patchright.sync_api import sync_playwright, Page, BrowserContext

PROFILE_DIR = os.path.join(paths.data_dir(), ".browser_profile")
CF_TIMEOUT = 20000

_playwright = None
_context: BrowserContext = None
_page: Page = None


def _clear_window_placement():
    """Remove saved window bounds from Chrome profile so --start-maximized takes effect."""
    prefs_path = os.path.join(PROFILE_DIR, "Default", "Preferences")
    if not os.path.exists(prefs_path):
        return
    try:
        with open(prefs_path, "r", encoding="utf-8") as f:
            prefs = json.load(f)
        if prefs.get("browser", {}).pop("window_placement", None) is not None:
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f)
    except Exception:
        pass


def start():
    global _playwright, _context, _page
    os.makedirs(PROFILE_DIR, exist_ok=True)
    _clear_window_placement()
    _playwright = sync_playwright().start()
    _context = _playwright.chromium.launch_persistent_context(
        PROFILE_DIR,
        channel="chrome",
        headless=False,
        viewport={"width": 1024, "height": 768},
        locale="en-US",
        timezone_id="America/New_York",
        args=[
            "--disable-notifications",
            "--disable-save-password-bubble",
            "--window-size=1024,768",
        ],
    )
    _page = _context.pages[0] if _context.pages else _context.new_page()
    print("[browser] Browser launched.")


def stop():
    global _playwright, _context, _page
    try:
        if _page:
            _page.close()
        if _context:
            _context.close()
        if _playwright:
            _playwright.stop()
    except Exception as e:
        print(f"[browser] Error during stop: {e}")
    finally:
        _page = _context = _playwright = None
        print("[browser] Browser stopped.")


def page() -> Page:
    return _page


def navigate(url: str) -> str:
    _page.goto(url, wait_until="domcontentloaded", timeout=30000)
    _wait_for_cloudflare()
    return _page.content()


def current_url() -> str:
    return _page.url


def is_cloudflare_challenge() -> bool:
    try:
        return "Just a moment" in _page.title()
    except Exception:
        return False


def _wait_for_cloudflare():
    try:
        _page.wait_for_function(
            """() => !document.title.includes('Just a moment') &&
                    !document.querySelector('#cf-spinner') &&
                    !document.querySelector('.cf-browser-verification')""",
            timeout=CF_TIMEOUT
        )
    except Exception:
        pass
