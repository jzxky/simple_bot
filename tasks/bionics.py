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


def load_bionics_state() -> dict:
    import config as cfg
    return cfg.load().get("bionics_state", {})


def save_bionics_state(updates: dict):
    import config as cfg
    c = cfg.load()
    c.setdefault("bionics_state", {}).update(updates)
    cfg.save(c)


# Keep old name so any other callers aren't broken
def load_last_bionics_check() -> float:
    return float(load_bionics_state().get("last_checked_at", 0))


def save_last_bionics_check(ts: float):
    save_bionics_state({"last_checked_at": ts})


class BionicsTask(Task):
    priority = 52
    label = "Bionics Store"

    def __init__(self):
        s = load_bionics_state()
        self.last_checked_at: float = float(s.get("last_checked_at", 0))
        self.last_stock: dict       = s.get("last_stock", {})
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

        # Time window check (handles midnight wrap)
        ingame = state.ingame_mins
        if b.get("use_time_window", False) and ingame is not None:
            start = b.get("window_start", "00:00")
            end   = b.get("window_end",   "23:59")
            start_mins = int(start[:2]) * 60 + int(start[3:])
            end_mins   = int(end[:2])   * 60 + int(end[3:])
            if start_mins < end_mins:
                in_window = start_mins < ingame < end_mins
            else:  # crosses midnight
                in_window = ingame > start_mins or ingame < end_mins
            if not in_window:
                return False

        return True

    def run(self, state: GameState, executor):
        executor.execute(Action("check_bionics", _task=self), state)
