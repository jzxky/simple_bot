"""
Patchright browser singleton. All bot tasks share one browser page.

Uses a persistent profile so Cloudflare trusts the session over time.
"""

import json
import os
from contextlib import contextmanager
import paths
from patchright.sync_api import sync_playwright, Page, BrowserContext

PROFILE_DIR = os.path.join(paths.data_dir(), ".browser_profile")
CF_TIMEOUT = 20000

_playwright = None
_context: BrowserContext = None
_page: Page = None
# Optional override so code written against page()/navigate()/current_url()
# can be pointed at a second tab (e.g. the aggravated-crimes tab) without
# threading a `page` argument through every call site. Set via use_page().
_active_page: "Page | None" = None


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


def start(headless: bool = False):
    global _playwright, _context, _page
    os.makedirs(PROFILE_DIR, exist_ok=True)
    _clear_window_placement()
    _playwright = sync_playwright().start()
    args = ["--disable-notifications", "--disable-save-password-bubble", "--disable-wake-lock"]
    DESKTOP_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    )
    if headless:
        args.append("--window-size=1920,1080")
        _context = _playwright.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=True,
            chromium_sandbox=True,
            viewport={"width": 1920, "height": 1080},
            user_agent=DESKTOP_UA,
            locale="en-US",
            timezone_id="America/New_York",
            args=args,
        )
    else:
        args.append("--start-maximized")
        _context = _playwright.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",
            headless=False,
            chromium_sandbox=True,
            no_viewport=True,
            locale="en-US",
            timezone_id="America/New_York",
            args=args,
        )
    _page = _context.pages[0] if _context.pages else _context.new_page()
    print("[browser] Browser launched.")


def stop():
    """Tear the browser down. Each step is isolated so a dead driver (where
    closing the page/context raises) still lets us stop playwright itself —
    otherwise the node driver process leaks and the next start() piles another
    one on top."""
    global _playwright, _context, _page, _active_page
    for label, fn in (
        ("page.close", lambda: _page and _page.close()),
        ("context.close", lambda: _context and _context.close()),
        ("playwright.stop", lambda: _playwright and _playwright.stop()),
    ):
        try:
            fn()
        except Exception as e:
            print(f"[browser] Error during stop ({label}): {e}")
    _page = _context = _playwright = _active_page = None
    print("[browser] Browser stopped.")


# Substrings that mean the browser, its page, or the patchright driver process
# is gone and nothing short of a full restart will recover it.
BROWSER_LOST_MARKERS = (
    "Connection closed while reading from the driver",
    "Target page, context or browser has been closed",
    "Browser has been closed",
    "Page crashed",
    "Target crashed",
    "has been closed",
    "ERR_INSUFFICIENT_RESOURCES",
)


def is_lost_error(err) -> bool:
    """True when an exception (or its message) indicates a dead browser/driver."""
    text = err if isinstance(err, str) else str(err)
    return any(marker in text for marker in BROWSER_LOST_MARKERS)


def is_alive() -> bool:
    """Cheap round-trip to the driver. False when the browser or driver died."""
    pg = page()
    if pg is None or _context is None:
        return False
    try:
        if pg.is_closed():
            return False
        _ = pg.url
        return True
    except Exception:
        return False


def page() -> Page:
    return _active_page or _page


def is_secondary_page_active() -> bool:
    """True while use_page() has page()/navigate()/current_url() pointed at a
    tab other than the main one."""
    return _active_page is not None


@contextmanager
def use_page(pg: Page):
    """Temporarily point page()/navigate()/current_url() at `pg` instead of the
    main tab, so existing code that calls browser.page() can be reused unchanged
    against a second tab (e.g. the aggravated-crimes tab). Not reentrant —
    nesting overwrites and then restores the previous override, which is fine
    since only one secondary tab drives at a time."""
    global _active_page
    prev = _active_page
    _active_page = pg
    try:
        yield pg
    finally:
        _active_page = prev


SCREENSHOT_PATH = os.path.join(paths.data_dir(), "last_screenshot.png")


def navigate(url: str) -> str:
    pg = page()
    for attempt in range(2):
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            break
        except Exception as e:
            if "ERR_ABORTED" in str(e) and attempt == 0:
                continue
            raise
    _wait_for_cloudflare_on(pg)
    try:
        pg.screenshot(path=SCREENSHOT_PATH, full_page=False)
    except Exception:
        pass
    return pg.content()


def current_url() -> str:
    return page().url


def is_cloudflare_challenge() -> bool:
    try:
        return "Just a moment" in _page.title()
    except Exception:
        return False


def _wait_for_cloudflare_on(pg: Page):
    try:
        pg.wait_for_function(
            """() => !document.title.includes('Just a moment') &&
                    !document.querySelector('#cf-spinner') &&
                    !document.querySelector('.cf-browser-verification')""",
            timeout=CF_TIMEOUT
        )
    except Exception:
        pass


def new_page() -> Page:
    return _context.new_page()


def close_page(pg: Page):
    try:
        pg.close()
    except Exception:
        pass


def navigate_page(pg: Page, url: str) -> str:
    for attempt in range(2):
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            break
        except Exception as e:
            if "ERR_ABORTED" in str(e) and attempt == 0:
                continue
            raise
    _wait_for_cloudflare_on(pg)
    return pg.content()
