"""
Patchright browser singleton. All bot tasks share one browser page.

Uses a persistent profile so Cloudflare trusts the session over time.
"""

import os
from patchright.sync_api import sync_playwright, Page, BrowserContext

PROFILE_DIR = os.path.join(os.path.dirname(__file__), ".browser_profile")
CF_TIMEOUT = 20000  # ms to wait for Cloudflare challenge to clear

_playwright = None
_context: BrowserContext = None
_page: Page = None


def start():
    global _playwright, _context, _page
    os.makedirs(PROFILE_DIR, exist_ok=True)
    _playwright = sync_playwright().start()
    _context = _playwright.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=False,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
    )
    _page = _context.new_page()
    print("[browser] Chrome launched.")


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
        print("[browser] Chrome stopped.")


def page() -> Page:
    return _page


def navigate(url: str) -> str:
    _page.goto(url, wait_until="domcontentloaded", timeout=30000)
    _wait_for_cloudflare()
    return _page.content()


def current_url() -> str:
    return _page.url


def _wait_for_cloudflare():
    """If Cloudflare challenge is present, wait for it to resolve."""
    try:
        # Cloudflare challenge pages contain this title or a cf-spinner element
        # Wait briefly — if challenge is gone quickly, we move on
        _page.wait_for_function(
            """() => !document.title.includes('Just a moment') &&
                    !document.querySelector('#cf-spinner') &&
                    !document.querySelector('.cf-browser-verification')""",
            timeout=CF_TIMEOUT
        )
    except Exception:
        # If it times out, proceed anyway — page may still be usable
        pass
