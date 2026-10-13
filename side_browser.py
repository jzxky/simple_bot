"""
Side browser — a second, fully independent patchright instance driven from its
own worker thread, so long-running tab work (top-job sniping, separate-tab
aggravated crimes) never waits on the main bot loop and never blocks it.

Patchright's sync API is bound to the thread that started it, and Chrome locks
a profile directory to one process, so this runs its own sync_playwright() and
its own Chrome window on a dedicated profile (.browser_profile_side). It shares
the main browser's login by importing the main context's cookies (session +
Cloudflare clearance) — no second login.

Jobs run one at a time, each in a fresh tab that it closes when done. The
browser itself launches on the first job and stays open until shutdown().

Threading contract:
  - submit(), cookies_requested(), provide_cookies(), cancel_current(),
    shutdown() are called from the main thread.
  - A job's fn(side, job) runs on the worker thread. It may only touch the
    patchright objects it gets from `side`, never browser.page() of the main
    browser (use browser.use_page() to point executor helpers at its own tab).
"""

import os
import queue
import threading
import paths

SIDE_PROFILE_DIR = os.path.join(paths.data_dir(), ".browser_profile_side")
COOKIE_WAIT_SECS = 30


class Job:
    def __init__(self, kind: str, fn, cookies: list, headless: bool = False):
        self.kind = kind
        self.fn = fn
        self.cookies = cookies
        self.headless = headless
        self.cancel = threading.Event()
        self.cancel_reason = ""
        self.done = threading.Event()

    def request_cancel(self, reason: str):
        if not self.cancel.is_set():
            self.cancel_reason = reason
            self.cancel.set()


class _Side:
    """Worker-thread handle passed to each job's fn."""

    def __init__(self):
        self._pw = None
        self._context = None

    def _ensure(self, headless: bool):
        if self._context is not None:
            return
        from patchright.sync_api import sync_playwright
        import browser
        self._pw = sync_playwright().start()
        try:
            self._context = browser.launch_context(self._pw, SIDE_PROFILE_DIR, headless)
        except Exception:
            self._stop_pw()
            raise

    def new_page(self, job: Job):
        self._ensure(job.headless)
        if job.cookies:
            self._context.add_cookies(job.cookies)
        return self._context.new_page()

    def refresh_cookies(self, job: Job) -> bool:
        """Ask the main thread for fresh cookies (e.g. after the session
        rotated) and load them. Returns False if none arrived in time."""
        cookies = _request_cookies(job)
        if not cookies:
            return False
        self._context.add_cookies(cookies)
        return True

    def close_page(self, pg):
        try:
            pg.close()
        except Exception:
            pass

    def teardown(self):
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
        self._stop_pw()

    def _stop_pw(self):
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None


_jobs: "queue.Queue[Job]" = queue.Queue()
_thread: "threading.Thread | None" = None
_shutdown = threading.Event()  # stop flag of the current worker; replaced per thread
_current: "Job | None" = None
_lock = threading.Lock()
_cookie_request = threading.Event()
_cookie_reply: queue.Queue = queue.Queue(maxsize=1)


def _request_cookies(job: Job) -> list:
    stop = _shutdown
    while not _cookie_reply.empty():
        _cookie_reply.get_nowait()
    _cookie_request.set()
    try:
        while True:
            try:
                return _cookie_reply.get(timeout=0.5)
            except queue.Empty:
                if job.cancel.is_set() or stop.is_set():
                    return []
                if not _cookie_request.is_set():
                    return []
    finally:
        _cookie_request.clear()


def _worker(stop: threading.Event):
    global _current
    import browser
    side = _Side()
    try:
        while not stop.is_set():
            try:
                job = _jobs.get(timeout=0.5)
            except queue.Empty:
                continue
            with _lock:
                _current = job
            try:
                job.fn(side, job)
            except Exception as e:
                # Jobs handle their own errors; this is a last-resort guard so
                # one bad job can't kill the worker. A dead browser is torn down
                # so the next job relaunches it.
                print(f"[side_browser] job {job.kind} crashed: {e}")
                if browser.is_lost_error(e):
                    side.teardown()
            finally:
                with _lock:
                    _current = None
                job.done.set()
    finally:
        side.teardown()
        # Anything still queued never ran — release whoever waits on it.
        while True:
            try:
                _jobs.get_nowait().done.set()
            except queue.Empty:
                break


def submit(kind: str, fn, cookies: list, headless: bool = False,
           preempt: bool = False) -> Job:
    """Queue `fn(side, job)` to run on the worker thread. With preempt=True the
    job currently running (if any) is asked to stop so this one starts next."""
    global _thread, _shutdown
    job = Job(kind, fn, cookies, headless)
    if _thread is None or not _thread.is_alive():
        _shutdown = threading.Event()
        _thread = threading.Thread(target=_worker, args=(_shutdown,), name="side-browser", daemon=True)
        _thread.start()
    if preempt:
        cancel_current(f"{kind} starting")
    _jobs.put(job)
    return job


def current_kind() -> str:
    with _lock:
        return _current.kind if _current else ""


def cancel_current(reason: str, kind: str = "") -> "Job | None":
    """Ask the running job (optionally only if it is of `kind`) to stop."""
    with _lock:
        job = _current
    if job is not None and (not kind or job.kind == kind):
        job.request_cancel(reason)
        return job
    return None


def cookies_requested() -> bool:
    return _cookie_request.is_set()


def provide_cookies(cookies: list):
    try:
        _cookie_reply.put_nowait(cookies)
    except queue.Full:
        pass


def shutdown(timeout: float = 15.0):
    """Stop the worker: cancel the running job, close the side browser, and
    wait (up to `timeout`) for the thread to exit."""
    global _thread
    _shutdown.set()
    cancel_current("bot stopping")
    _cookie_request.clear()
    t = _thread
    if t is not None and t.is_alive() and t is not threading.current_thread():
        t.join(timeout)
    _thread = None
