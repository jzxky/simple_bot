"""
Checks the Chicago bionics store for wanted items and purchases them.

Runs when: logged in, not in jail/hospital, in Chicago, enabled in config,
enough in-game time has passed since last check, and (if use_time_window)
in-game time is within the configured window.

Purchase order: heart → brain → eyes → legs → arms (most expensive first).
Withdraws cash before each navigation to the store.
"""

import re
import time
from datetime import datetime
from tasks.base import Task, Action
from state import GameState

# Known fixed prices — used for pre-withdrawal decisions
BIONIC_PRICES = {"arms": 10000, "legs": 20000, "eyes": 35000, "brain": 50000, "heart": 50000}
REVERSE_ORDER  = ["heart", "brain", "eyes", "legs", "arms"]


def _ingame_mins(page_content: str) -> "int | None":
    """Parse div.serverTime and return minutes-since-midnight, or None."""
    m = re.search(r'class="serverTime"[^>]*>([^<]+)<', page_content)
    if not m:
        return None
    parts = m.group(1).strip().split(" ", 1)
    if len(parts) < 2:
        return None
    try:
        dt = datetime.strptime(parts[1], "%I:%M:%S %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        return None


def _mins_elapsed(last: int, now: int) -> int:
    diff = now - last
    return diff if diff >= 0 else diff + 1440  # midnight wrap


class BionicsTask(Task):
    priority = 52
    label = "Bionics Store"

    def __init__(self):
        self.last_checked_ingame: "int | None" = None
        self.last_views: "tuple[int,int] | None" = None

    def can_run(self, state: GameState) -> bool:
        import config as cfg
        import browser
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.current_city.lower() != "chicago":
            return False
        b = cfg.load().get("bionics", {})
        if not b.get("enabled", False):
            return False

        interval_mins = int(b.get("check_interval_minutes", 5))
        try:
            ingame = _ingame_mins(browser.page().content())
        except Exception:
            ingame = None

        # Interval check (in-game time based)
        if ingame is not None and self.last_checked_ingame is not None:
            if _mins_elapsed(self.last_checked_ingame, ingame) < interval_mins:
                return False

        # Time window check
        if b.get("use_time_window", False) and ingame is not None:
            start = b.get("window_start", "00:00")
            end   = b.get("window_end",   "23:59")
            start_mins = int(start[:2]) * 60 + int(start[3:])
            end_mins   = int(end[:2])   * 60 + int(end[3:])
            if not (start_mins < ingame < end_mins):
                return False

        return True

    def run(self, state: GameState, executor):
        executor.execute(Action("check_bionics", _task=self), state)
