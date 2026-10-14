"""
Side browser — a second, fully independent patchright instance driven from its
own worker thread, so long-running tab work (top-job sniping, separate-tab
aggravated crimes) never waits on the main bot loop and never blocks it.

Patchright's sync API is bound to the thread that started it, and Chrome locks
a profile directory to one process, so this runs its own sync_playwright() and
its own Chrome window on a dedicated profile (.browser_profile_side). It shares
the main browser's login by importing the main context's cookies (session +
Cloudflare clearance) — no second login.

Work is split into lanes ("snipe", "crime"), each its own worker thread with
its own Chrome window and profile (.browser_profile_side_<lane>), so a top-job
snipe and a crime run can go at the same time without waiting on each other.
Within a lane, jobs run one at a time, each in a fresh tab that it closes when
done. A lane's browser launches on its first job and stays open until
shutdown().

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

SIDE_PROFILE_DIR = os.path.join(paths.data_dir(), ".browser_profile_side")  # + "_<lane>"


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

    def __init__(self, lane: "_Lane"):
        self._lane = lane
        self._pw = None
        self._context = None

    def _ensure(self, headless: bool):
        if self._context is not None:
            return
        from patchright.sync_api import sync_playwright
        import browser
        self._pw = sync_playwright().start()
        try:
            self._context = browser.launch_context(self._pw, f"{SIDE_PROFILE_DIR}_{self._lane.name}", headless)
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
        cookies = self._lane.request_cookies(job)
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


class _Lane:
    def __init__(self, name: str):
        self.name = name
        self.jobs: "queue.Queue[Job]" = queue.Queue()
        self.thread: "threading.Thread | None" = None
        self.stop = threading.Event()  # replaced per worker thread
        self.current: "Job | None" = None
        self.lock = threading.Lock()
        self.cookie_request = threading.Event()
        self.cookie_reply: queue.Queue = queue.Queue(maxsize=1)

    # ---- worker thread ----

    def request_cookies(self, job: Job) -> list:
        stop = self.stop
        while not self.cookie_reply.empty():
            self.cookie_reply.get_nowait()
        self.cookie_request.set()
        try:
            while True:
                try:
                    return self.cookie_reply.get(timeout=0.5)
                except queue.Empty:
                    if job.cancel.is_set() or stop.is_set():
                        return []
                    if not self.cookie_request.is_set():
                        return []
        finally:
            self.cookie_request.clear()

    def run(self, stop: threading.Event):
        import browser
        side = _Side(self)
        try:
            while not stop.is_set():
                try:
                    job = self.jobs.get(timeout=0.5)
                except queue.Empty:
                    continue
                with self.lock:
                    self.current = job
                try:
                    job.fn(side, job)
                except Exception as e:
                    # Jobs handle their own errors; this is a last-resort guard so
                    # one bad job can't kill the worker. A dead browser is torn
                    # down so the next job relaunches it.
                    print(f"[side_browser:{self.name}] job {job.kind} crashed: {e}")
                    if browser.is_lost_error(e):
                        side.teardown()
                finally:
                    with self.lock:
                        self.current = None
                    job.done.set()
        finally:
            side.teardown()
            # Anything still queued never ran — release whoever waits on it.
            while True:
                try:
                    self.jobs.get_nowait().done.set()
                except queue.Empty:
                    break

    # ---- main thread ----

    def submit(self, job: Job):
        if self.thread is None or not self.thread.is_alive():
            self.stop = threading.Event()
            self.thread = threading.Thread(target=self.run, args=(self.stop,),
                                           name=f"side-browser-{self.name}", daemon=True)
            self.thread.start()
        self.jobs.put(job)

    def cancel_current(self, reason: str, kind: str = "") -> "Job | None":
        with self.lock:
            job = self.current
        if job is not None and (not kind or job.kind == kind):
            job.request_cancel(reason)
            return job
        return None

    def shutdown(self, timeout: float):
        self.stop.set()
        self.cancel_current("bot stopping")
        self.cookie_request.clear()
        t = self.thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout)
        self.thread = None


_lanes: "dict[str, _Lane]" = {}
_lanes_lock = threading.Lock()


def _lane(name: str) -> _Lane:
    with _lanes_lock:
        if name not in _lanes:
            _lanes[name] = _Lane(name)
        return _lanes[name]


def submit(lane: str, kind: str, fn, cookies: list, headless: bool = False) -> Job:
    """Queue `fn(side, job)` to run on `lane`'s worker thread."""
    job = Job(kind, fn, cookies, headless)
    _lane(lane).submit(job)
    return job


def cancel_current(lane: str, reason: str, kind: str = "") -> "Job | None":
    """Ask the job running on `lane` (optionally only if it is of `kind`) to stop."""
    return _lane(lane).cancel_current(reason, kind)


def cookies_requested() -> bool:
    with _lanes_lock:
        lanes = list(_lanes.values())
    return any(l.cookie_request.is_set() for l in lanes)


def provide_cookies(cookies: list):
    """Hand fresh cookies to every lane that asked for them."""
    with _lanes_lock:
        lanes = list(_lanes.values())
    for l in lanes:
        if l.cookie_request.is_set():
            try:
                l.cookie_reply.put_nowait(cookies)
            except queue.Full:
                pass


def shutdown(timeout: float = 15.0):
    """Stop every lane: cancel running jobs, close the side browsers, and wait
    (up to `timeout` each) for the threads to exit."""
    with _lanes_lock:
        lanes = list(_lanes.values())
    for l in lanes:
        l.stop.set()
        l.cancel_current("bot stopping")
    for l in lanes:
        l.shutdown(timeout)
