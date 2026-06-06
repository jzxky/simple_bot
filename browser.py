"""
Playwright browser singleton. All bot tasks share one browser page.
"""

from patchright.sync_api import sync_playwright, Page, Browser, BrowserContext

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
)

_playwright = None
_browser: Browser = None
_context: BrowserContext = None
_page: Page = None


def start():
    global _playwright, _browser, _context, _page
    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(headless=True)
    _context = _browser.new_context(user_agent=MOBILE_UA)
    _page = _context.new_page()


def stop():
    global _playwright, _browser, _context, _page
    if _page:
        _page.close()
    if _context:
        _context.close()
    if _browser:
        _browser.close()
    if _playwright:
        _playwright.stop()
    _page = _context = _browser = _playwright = None


def page() -> Page:
    return _page


def navigate(url: str) -> str:
    _page.goto(url, wait_until="domcontentloaded")
    return _page.content()


def current_url() -> str:
    return _page.url
