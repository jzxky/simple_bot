"""
Checks the Chicago bionics store for wanted items and purchases them.

Runs when: logged in, not in jail/hospital, in Chicago, enabled in config,
enough in-game time has passed since last check, and (if use_time_window)
in-game time is within the configured window.

Purchase order: heart → brain → eyes → legs → arms (most expensive first).
Withdraws cash before each navigation to the store.
"""

import time
from tasks.base import Task, Action
from state import GameState

# Known fixed prices — used for pre-withdrawal decisions
BIONIC_PRICES = {"arms": 10000, "legs": 20000, "eyes": 35000, "brain": 50000, "heart": 50000}
REVERSE_ORDER  = ["heart", "brain", "eyes", "legs", "arms"]



def _mins_elapsed(last: int, now: int) -> int:
    diff = now - last
    return diff if diff >= 0 else diff + 1440  # midnight wrap


class BionicsTask(Task):
    priority = 52
    label = "Bionics Store"

    def __init__(self):
        self.last_checked_ingame: "int | None" = None  # minutes since midnight
        self.next_check_at: "float | None" = None      # Unix timestamp
        self.last_views: "tuple[int,int] | None" = None

    def can_run(self, state: GameState) -> bool:
        import config as cfg
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.current_city.lower() != "chicago":
            return False
        b = cfg.load().get("bionics", {})
        if not b.get("enabled", False):
            return False

        ingame = state.ingame_mins
        interval_mins = int(b.get("check_interval_minutes", 5))

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
