"""
Patchright browser singleton. All bot tasks share one browser page.

Uses a persistent profile so Cloudflare trusts the session over time.
"""

import json
import os
import threading
import time
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
# Thread-local so the side-browser worker thread (side_browser.py) can point
# page() at its own tab without redirecting the main thread's navigations.
_local = threading.local()
_main_thread: "threading.Thread | None" = None

_NAV_FAIL_THRESHOLD = 3
_nav_fail_count = 0
_started_at: float = 0.0


def _clear_window_placement(profile_dir: str):
    """Remove saved window bounds from Chrome profile so --start-maximized takes effect."""
    prefs_path = os.path.join(profile_dir, "Default", "Preferences")
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


_DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def _launch_options(headless: bool) -> "tuple[dict, dict]":
    """(launch options, context options) shared by every browser the bot opens."""
    # --disable-quic: Chrome's HTTP/3 (QUIC over UDP) connections to the
    # Cloudflare-fronted site intermittently die with ERR_QUIC_PROTOCOL_ERROR;
    # plain HTTP/2 over TCP is reliable.
    args = ["--disable-notifications", "--disable-save-password-bubble", "--disable-wake-lock",
            "--disable-quic"]
    launch = {
        "channel": "chrome",
        "headless": headless,
        "chromium_sandbox": True,
        "args": args,
        # Patchright adds this by default; Chrome then shows an "unsupported
        # command-line flag" infobar. Strip it from the default args.
        "ignore_default_args": ["--disable-blink-features=AutomationControlled"],
    }
    ctx = {"locale": "en-US", "timezone_id": "America/New_York"}
    if headless:
        args.append("--window-size=1920,1080")
        ctx.update(viewport={"width": 1920, "height": 1080}, user_agent=_DESKTOP_UA)
    else:
        args.append("--start-maximized")
        ctx.update(no_viewport=True)
    return launch, ctx


def launch_context(pw, profile_dir: str, headless: bool = False) -> BrowserContext:
    """Launch the main browser: a persistent Chrome context on `profile_dir`
    with the bot's standard settings."""
    os.makedirs(profile_dir, exist_ok=True)
    _clear_window_placement(profile_dir)
    launch, ctx = _launch_options(headless)
    return pw.chromium.launch_persistent_context(profile_dir, **launch, **ctx)


def launch_ephemeral_context(pw, headless: bool = False):
    """Launch a Chrome with a throwaway profile that leaves nothing on disk,
    for the side browsers (they borrow the main browser's cookies, so they
    have nothing worth keeping). Returns (browser, context); close both."""
    launch, ctx = _launch_options(headless)
    br = pw.chromium.launch(**launch)
    try:
        return br, br.new_context(**ctx)
    except Exception:
        try:
            br.close()
        except Exception:
            pass
        raise


def start(headless: bool = False):
    global _playwright, _context, _page, _main_thread, _started_at
    _main_thread = threading.current_thread()
    _playwright = sync_playwright().start()
    _context = launch_context(_playwright, PROFILE_DIR, headless)
    _page = _context.pages[0] if _context.pages else _context.new_page()
    global _nav_fail_count
    _nav_fail_count = 0
    _started_at = time.monotonic()
    print("[browser] Browser launched.")


def stop():
    """Tear the browser down. Each step is isolated so a dead driver (where
    closing the page/context raises) still lets us stop playwright itself —
    otherwise the node driver process leaks and the next start() piles another
    one on top."""
    global _playwright, _context, _page
    for label, fn in (
        ("page.close", lambda: _page and _page.close()),
        ("context.close", lambda: _context and _context.close()),
        ("playwright.stop", lambda: _playwright and _playwright.stop()),
    ):
        try:
            fn()
        except Exception as e:
            print(f"[browser] Error during stop ({label}): {e}")
    _page = _context = _playwright = None
    print("[browser] Browser stopped.")


# ---------------------------------------------------------------------------
# Restart with crash-loop protection
# ---------------------------------------------------------------------------

# Two restarts closer together than this count as one crash streak.
_RESTART_STREAK_WINDOW = 180.0
_RESTART_BACKOFF_BASE = 30.0
_RESTART_BACKOFF_MAX = 600.0
_last_restart_at: float = 0.0
_restart_streak = 0

# Disposable Chrome caches inside the profile. A corrupt cache or a bloated
# GPU/code cache can make every fresh renderer crash on its first page load,
# so they are cleared once the browser keeps dying right after a restart.
# Cookies, Local Storage and the rest of the profile are left alone.
_CACHE_DIRS = (
    "Cache", "Code Cache", "GPUCache", "DawnCache", "DawnGraphiteCache",
    "DawnWebGPUCache", "GrShaderCache", "GraphiteDawnCache", "ShaderCache",
    os.path.join("Service Worker", "CacheStorage"),
    os.path.join("Service Worker", "ScriptCache"),
)


def _clear_profile_caches(profile_dir: str) -> int:
    import shutil
    removed = 0
    for base in (profile_dir, os.path.join(profile_dir, "Default")):
        for name in _CACHE_DIRS:
            path = os.path.join(base, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
    return removed


def restart_streak() -> int:
    """How many restarts in a row came close together (1 = an isolated one)."""
    return _restart_streak


def restart(headless: bool, log, wait=None) -> bool:
    """Tear the main browser down and relaunch it, without spinning when the
    browser keeps dying straight after a restart (e.g. the machine is out of
    memory: ERR_INSUFFICIENT_RESOURCES / "Page crashed" on every new page).

    A first restart happens right away. If the browser dies again within a
    few minutes of the last restart, this:
      - closes the side browsers (snipe / crime / drug windows) to free memory,
      - clears Chrome's disposable caches in the profile,
      - waits before relaunching, doubling the wait each time (30s, 60s, ...
        up to 10 min).

    `log` is called with progress messages. `wait(seconds)` is used for the
    backoff and should return True when the bot is stopping (e.g. an Event's
    wait); the restart is then abandoned. Returns True if the browser came up."""
    global _last_restart_at, _restart_streak
    now = time.monotonic()
    if _last_restart_at and now - _last_restart_at < _RESTART_STREAK_WINDOW:
        _restart_streak += 1
    else:
        _restart_streak = 1

    stop()
    if _restart_streak >= 2:
        delay = min(_RESTART_BACKOFF_BASE * (2 ** (_restart_streak - 2)), _RESTART_BACKOFF_MAX)
        try:
            import side_browser
            side_browser.shutdown()
        except Exception as e:
            print(f"[browser] Error shutting down side browsers: {e}")
        cleared = _clear_profile_caches(PROFILE_DIR)
        log(f"Browser crashed again shortly after a restart ({_restart_streak} in a row) — "
            f"closed side windows{', cleared browser cache' if cleared else ''}, "
            f"waiting {int(delay)}s before relaunching.")
        if wait is not None:
            if wait(delay):
                return False
        else:
            time.sleep(delay)
    else:
        # Give the old Chrome processes a moment to exit and release the profile.
        time.sleep(2)

    try:
        start(headless=headless)
    except Exception as e:
        log(f"Browser restart failed: {e}")
        return False
    finally:
        # Measured from when the browser came back, so a long backoff wait
        # doesn't make the next quick crash look like a fresh, isolated one.
        _last_restart_at = time.monotonic()
    log("Browser restarted — will re-login on next tick.")
    return True


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


def uptime_seconds() -> float:
    """Seconds since the main browser was last (re)launched; 0 when not running."""
    if _context is None:
        return 0.0
    return time.monotonic() - _started_at


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


def _on_main_thread() -> bool:
    return _main_thread is None or threading.current_thread() is _main_thread


def record_nav_failure():
    # The failure counter drives restarts of the main browser — the side
    # browser's navigations must not touch it.
    global _nav_fail_count
    if _on_main_thread():
        _nav_fail_count += 1


def record_nav_success():
    global _nav_fail_count
    if _on_main_thread():
        _nav_fail_count = 0


def should_restart_for_nav_failures() -> bool:
    return _nav_fail_count >= _NAV_FAIL_THRESHOLD


def page() -> Page:
    return getattr(_local, "page", None) or _page


def is_secondary_page_active() -> bool:
    """True while use_page() has page()/navigate()/current_url() pointed at a
    tab other than the main one, on the calling thread."""
    return getattr(_local, "page", None) is not None


@contextmanager
def use_page(pg: Page):
    """Temporarily point page()/navigate()/current_url() at `pg` instead of the
    main tab, for the calling thread only, so existing code that calls
    browser.page() can be reused unchanged against another tab (the drug store
    tab on the main thread, or a side-browser tab on the worker thread)."""
    prev = getattr(_local, "page", None)
    _local.page = pg
    try:
        yield pg
    finally:
        _local.page = prev


def export_cookies() -> list:
    """Main browser's cookies (session + Cloudflare clearance), for seeding the
    side browser. Main thread only — patchright objects are thread-bound."""
    return _context.cookies() if _context is not None else []


SCREENSHOT_PATH = os.path.join(paths.data_dir(), "last_screenshot.png")


# Network errors that are usually a one-off blip (dropped connection, protocol
# hiccup) rather than a real problem with the page — worth one more try.
_TRANSIENT_NAV_ERRORS = (
    "ERR_ABORTED",
    "ERR_QUIC_PROTOCOL_ERROR",
    "ERR_HTTP2_PROTOCOL_ERROR",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_EMPTY_RESPONSE",
    "ERR_NETWORK_CHANGED",
)


_FORCE_CHECK_JS = """el => {
    el.checked = true;
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
}"""


def check_radio(pg: Page, selector: str, timeout: "float | None" = None):
    """Select a radio button, with a failsafe. page.check() can fail with
    "Clicking the checkbox did not change its state" when the page's own
    script swallows the click; in that case set it in the page and fire the
    events a click would. Raises the original error only if the radio still
    isn't selected afterwards (so callers behave as with page.check())."""
    try:
        if timeout is None:
            pg.check(selector)  # default wait, same as a plain page.check()
        else:
            pg.check(selector, timeout=timeout)
        return
    except Exception as e:
        err = e
    try:
        pg.eval_on_selector(selector, _FORCE_CHECK_JS)
        if pg.eval_on_selector(selector, "el => el.checked"):
            return
    except Exception:
        pass
    raise err


def _goto_with_retry(pg: Page, url: str):
    attempts = 3
    for attempt in range(attempts):
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            return
        except Exception as e:
            err = str(e)
            if attempt < attempts - 1 and any(code in err for code in _TRANSIENT_NAV_ERRORS):
                time.sleep(1 + attempt)
                continue
            raise


def navigate(url: str) -> str:
    pg = page()
    _goto_with_retry(pg, url)
    record_nav_success()
    _wait_for_cloudflare_on(pg)
    if _on_main_thread():  # don't let the side browser race the main one for the file
        try:
            pg.screenshot(path=SCREENSHOT_PATH, full_page=False)
        except Exception:
            pass
        capture_if_watched(force=True)
    return pg.content()


def current_url() -> str:
    return page().url


# ---------------------------------------------------------------------------
# Watching: view-only screenshots of the main browser (e.g. the live view
# plugin's Watch mode). Patchright objects belong to the bot thread, so frames
# are only taken there: after each navigate() and on every bot loop tick.
# ---------------------------------------------------------------------------

WATCH_EVERY = 1.0           # at most one frame a second
_watch_cond = threading.Condition()
_watch_until = 0.0
_watch_last = 0.0
_watch_frame = (0, b"", "")  # (seq, jpeg, url)


def want_frames(seconds: float = 10.0):
    """Someone is watching: take frames for the next `seconds`."""
    global _watch_until
    with _watch_cond:
        _watch_until = max(_watch_until, time.monotonic() + seconds)


def capture_if_watched(force: bool = False):
    """Bot thread only. Take a frame of the main page if someone is watching."""
    global _watch_last, _watch_frame
    now = time.monotonic()
    if not _on_main_thread() or is_secondary_page_active() or _page is None:
        return
    with _watch_cond:
        if now >= _watch_until or (not force and now - _watch_last < WATCH_EVERY):
            return
    try:
        img = _page.screenshot(type="jpeg", quality=60, scale="css", timeout=5000)
        url = _page.url
    except Exception:
        return
    with _watch_cond:
        _watch_last = now
        _watch_frame = (_watch_frame[0] + 1, img, url)
        _watch_cond.notify_all()


def watch_frame(after: int = -1, wait: float = 0.0):
    """(seq, jpeg, url) of the latest frame, waiting up to `wait` seconds for
    one newer than `after`."""
    with _watch_cond:
        if _watch_frame[0] <= after and wait > 0:
            _watch_cond.wait(wait)
        return _watch_frame


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
    _goto_with_retry(pg, url)
    record_nav_success()
    _wait_for_cloudflare_on(pg)
    return pg.content()
