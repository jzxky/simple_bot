"""
Patchright browser singleton. All bot tasks share one browser page.

Uses a persistent profile so Cloudflare trusts the session over time.
"""

import os
import paths
from patchright.sync_api import sync_playwright, Page, BrowserContext

PROFILE_DIR = os.path.join(paths.data_dir(), ".browser_profile")
CF_TIMEOUT = 20000

_playwright = None
_context: BrowserContext = None
_page: Page = None


def start():
    global _playwright, _context, _page
    os.makedirs(PROFILE_DIR, exist_ok=True)
    _playwright = sync_playwright().start()
    _context = _playwright.chromium.launch_persistent_context(
        PROFILE_DIR,
        channel="chrome",
        headless=False,
        viewport=None,
        locale="en-US",
        timezone_id="America/New_York",
        args=[
            "--disable-notifications",
            "--disable-save-password-bubble",
            "--start-maximized",
        ],
    )
    _page = _context.pages[0] if _context.pages else _context.new_page()
    # Sync viewport to the actual window size so the page renders at full width
    try:
        w = _page.evaluate("() => window.outerWidth") or 1920
        h = _page.evaluate("() => window.outerHeight") or 1080
        _page.set_viewport_size({"width": w, "height": h})
    except Exception:
        _page.set_viewport_size({"width": 1920, "height": 1080})
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
