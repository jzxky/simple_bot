"""
Checks the Chicago bionics store for wanted items and purchases them.

Runs when: logged in, not in jail/hospital, in Chicago, enabled in config,
enough wall-clock time has passed since last check, and (if use_time_window)
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


def load_last_bionics_check() -> float:
    """Return the Unix timestamp of the last bionics check, or 0 if never."""
    import config as cfg
    return float(cfg.load().get("bionics_state", {}).get("last_checked_at", 0))


def save_last_bionics_check(ts: float):
    import config as cfg
    c = cfg.load()
    c.setdefault("bionics_state", {})["last_checked_at"] = ts
    cfg.save(c)


class BionicsTask(Task):
    priority = 52
    label = "Bionics Store"

    def __init__(self):
        self.last_checked_at: float = load_last_bionics_check()
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

        interval_secs = int(b.get("check_interval_minutes", 5)) * 60
        if self.last_checked_at > 0 and time.time() - self.last_checked_at < interval_secs:
            return False

        # Time window check
        ingame = state.ingame_mins
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
