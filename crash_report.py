"""
Crash reports: a snapshot of what the machine and the browser looked like when
Chrome crashed, the driver died or a page timed out, for troubleshooting.

Each report is a folder under logs/crash_reports/<time>_<kind>/ holding
report.txt (error, URL, memory, Chrome processes, recent log lines) and, when
the page still answers, page.png and page.html. A one-line summary also goes
to the bot log so it shows in the UI.

Bot thread only for the page parts (patchright objects are thread-bound).
Never raises: diagnostics must not make a bad situation worse.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime

import paths

REPORTS_DIR = os.path.join(paths.data_dir(), "logs", "crash_reports")
KEEP_REPORTS = 40
# Per kind: a crash loop or a run of timeouts shouldn't write a report every tick.
_MIN_GAP = {"crash": 30.0, "restart_failed": 30.0, "timeout": 300.0}
_last_by_kind: "dict[str, float]" = {}
_lock = threading.Lock()
# Recent tab crashes seen through the page "crash" event (time, url).
_tab_crashes: list = []


def note_tab_crash(url: str):
    """Called from the page's "crash" event handler."""
    with _lock:
        _tab_crashes.append((datetime.now().strftime("%H:%M:%S"), url or "?"))
        del _tab_crashes[:-20]


# ---------------------------------------------------------------------------
# Machine facts
# ---------------------------------------------------------------------------

def _fmt_mb(mb: float) -> str:
    return f"{mb / 1024:.1f} GB" if mb >= 1024 else f"{mb:.0f} MB"


def system_memory() -> "tuple[float, float] | None":
    """(free MB, total MB), or None if unknown."""
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return None
            return st.ullAvailPhys / 2**20, st.ullTotalPhys / 2**20
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":", 1)
                info[k] = float(v.split()[0]) / 1024
        return info.get("MemAvailable", info.get("MemFree", 0)), info["MemTotal"]
    except Exception:
        return None


def chrome_processes() -> "tuple[int, float] | None":
    """(count, total MB of working set) for every Chrome process, or None."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            count, kb = 0, 0
            for line in out.splitlines():
                cols = [c.strip('"') for c in line.split('","')]
                if len(cols) >= 5 and cols[0].lower() == "chrome.exe":
                    count += 1
                    kb += int("".join(ch for ch in cols[4] if ch.isdigit()) or 0)
            return count, kb / 1024
        out = subprocess.run(["ps", "-A", "-o", "rss=,comm="], capture_output=True,
                             text=True, timeout=10).stdout
        count, kb = 0, 0
        for line in out.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and "chrome" in parts[1].lower():
                count += 1
                kb += int(parts[0])
        return count, kb / 1024
    except Exception:
        return None


def disk_free_mb() -> "float | None":
    try:
        return shutil.disk_usage(paths.data_dir()).free / 2**20
    except Exception:
        return None


def resource_summary() -> str:
    """One line for the bot log, e.g. 'RAM 1.2 GB free of 8.0 GB · Chrome 14 processes, 2.3 GB'."""
    parts = []
    mem = system_memory()
    if mem:
        parts.append(f"RAM {_fmt_mb(mem[0])} free of {_fmt_mb(mem[1])}")
    ch = chrome_processes()
    if ch:
        parts.append(f"Chrome {ch[0]} processes, {_fmt_mb(ch[1])}")
    disk = disk_free_mb()
    if disk is not None and disk < 2048:
        parts.append(f"disk {_fmt_mb(disk)} free")
    return " · ".join(parts) or "resource usage unknown"


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def _prune():
    try:
        names = sorted(n for n in os.listdir(REPORTS_DIR)
                       if os.path.isdir(os.path.join(REPORTS_DIR, n)))
        for n in names[:-KEEP_REPORTS]:
            shutil.rmtree(os.path.join(REPORTS_DIR, n), ignore_errors=True)
    except Exception:
        pass


def capture(kind: str, error, state=None, action: str = "", with_page: bool = True) -> "str | None":
    """Write a crash report. `kind` is "crash", "timeout" or "restart_failed".
    Returns the report folder, or None if skipped (rate limit) or it failed.
    Logs a one-line summary through state.add_log when `state` is given."""
    try:
        now = time.monotonic()
        with _lock:
            gap = _MIN_GAP.get(kind, 30.0)
            if now - _last_by_kind.get(kind, -1e9) < gap:
                return None
            _last_by_kind[kind] = now
            tab_crashes = list(_tab_crashes)
        import browser

        summary = resource_summary()
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        folder = os.path.join(REPORTS_DIR, f"{stamp}_{kind}")
        os.makedirs(folder, exist_ok=True)

        url = ""
        page_note = "not captured"
        pg = browser.page()
        if pg is not None:
            try:
                url = pg.url
            except Exception:
                pass
        if with_page and pg is not None and browser._on_main_thread():
            try:
                pg.screenshot(path=os.path.join(folder, "page.png"), timeout=5000)
                with open(os.path.join(folder, "page.html"), "w", encoding="utf-8") as f:
                    f.write(pg.content())
                page_note = "page.png, page.html"
            except Exception as e:
                page_note = f"page did not answer ({str(e).splitlines()[0][:120]})"

        lines = [
            f"Kind:             {kind}",
            f"Time:             {datetime.now().isoformat(timespec='seconds')}",
            f"Action:           {action or '-'}",
            f"URL:              {url or '-'}",
            f"Resources:        {summary}",
            f"Browser uptime:   {int(browser.uptime_seconds())} s",
            f"Restart streak:   {browser.restart_streak()}",
            f"Nav failures:     {browser._nav_fail_count}",
            f"Threads:          {', '.join(sorted(t.name for t in threading.enumerate()))}",
            f"Platform:         {sys.platform}, Python {sys.version.split()[0]}",
            f"Page snapshot:    {page_note}",
        ]
        if state is not None:
            lines += [
                f"Logged in:        {getattr(state, 'logged_in', '?')}",
                f"City:             {getattr(state, 'current_city', '?')}",
                f"Current task:     {getattr(state, 'current_task', '') or '-'}",
                f"Side windows:     snipe={getattr(state, 'snipe_active', '?')} "
                f"crime={getattr(state, 'agg_tab_active', '?')} drugs={getattr(state, 'drug_tab_active', '?')}",
            ]
        if tab_crashes:
            lines += ["", "Recent tab crashes:"] + [f"  {t} {u}" for t, u in tab_crashes]
        lines += ["", "Error:", str(error)]
        if isinstance(error, BaseException) and error.__traceback__ is not None:
            lines += ["", "Traceback:", "".join(traceback.format_exception(type(error), error, error.__traceback__))]
        if state is not None:
            lines += ["", "Last log lines:"] + list(getattr(state, "log", [])[-60:])
        with open(os.path.join(folder, "report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        _prune()
        if state is not None:
            rel = os.path.relpath(folder, paths.data_dir())
            state.add_log(f"Crash report saved to {rel} — {summary}.")
        return folder
    except Exception as e:
        print(f"[crash_report] Could not write report: {e}")
        return None
