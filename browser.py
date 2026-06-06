"""
Patchright browser singleton. All bot tasks share one browser page.

Uses a persistent profile so Cloudflare trusts the session over time.
Attempts to use the system-installed Chrome before falling back to
the patchright-managed Chromium download.
"""

import os
import sys
import config as cfg
from patchright.sync_api import sync_playwright, Page, BrowserContext

PROFILE_DIR = os.path.join(os.path.dirname(__file__), ".browser_profile")
CF_TIMEOUT = 20000

_playwright = None
_context: BrowserContext = None
_page: Page = None

_CHROME_PATHS = {
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/snap/bin/chromium",
    ],
}


class ChromeNotFoundError(Exception):
    pass


def _find_chrome() -> str:
    # Check custom path from config first
    custom = cfg.load().get("bot_config", {}).get("chrome_path", "").strip()
    if custom:
        if os.path.isfile(custom):
            print(f"[browser] Using custom Chrome path: {custom}")
            return custom
        raise ChromeNotFoundError(
            f"Custom Chrome path not found: '{custom}'. "
            "Please check the path in Bot Config settings."
        )

    # Auto-detect by OS
    platform = sys.platform
    if platform.startswith("linux"):
        platform = "linux"
    for path in _CHROME_PATHS.get(platform, []):
        if os.path.isfile(path):
            print(f"[browser] Using system Chrome: {path}")
            return path

    raise ChromeNotFoundError(
        "Chrome could not be found on your system. "
        "Please install Google Chrome or set a custom path in Bot Config settings."
    )


def start():
    global _playwright, _context, _page
    os.makedirs(PROFILE_DIR, exist_ok=True)
    _playwright = sync_playwright().start()
    _context = _playwright.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=False,
        executable_path=_find_chrome(),
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
        args=[
            "--disable-notifications",
            "--disable-save-password-bubble",
        ],
        ignore_https_errors=True,
    )
    # Deny notification permission globally
    _context.grant_permissions([], origin="https://mafiamatrix.com")
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
        _page.wait_for_function(
            """() => !document.title.includes('Just a moment') &&
                    !document.querySelector('#cf-spinner') &&
                    !document.querySelector('.cf-browser-verification')""",
            timeout=CF_TIMEOUT
        )
    except Exception:
        pass
