"""
Checks the Auckland weapon store for wanted items and purchases them.

Runs when: logged in, not in jail/hospital, in Auckland, enabled in config,
enough wall-clock time has passed since last check, and (if use_time_window)
in-game time is within the configured window.

Purchase order follows config priority_order; if empty, uses store appearance order
for wanted items.
"""

import time
from tasks.base import Task, Action
from state import GameState


def load_weapon_store_state() -> dict:
    import config as cfg
    return cfg.load().get("weapon_store_state", {})


def save_weapon_store_state(updates: dict):
    import config as cfg
    c = cfg.load()
    c.setdefault("weapon_store_state", {}).update(updates)
    cfg.save(c)


class WeaponStoreTask(Task):
    priority = 51
    label = "Weapon Store"

    def __init__(self):
        s = load_weapon_store_state()
        self.last_checked_at: float = float(s.get("last_checked_at", 0))
        self.last_stock: dict = s.get("last_stock", {})
        self.last_views: "tuple[int,int] | None" = None

    def can_run(self, state: GameState) -> bool:
        import config as cfg
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.current_city.lower() != "auckland":
            return False
        w = cfg.load().get("weapon_store", {})
        if not w.get("enabled", False):
            return False

        interval_secs = int(w.get("check_interval_minutes", 5)) * 60
        if self.last_checked_at > 0 and time.time() - self.last_checked_at < interval_secs:
            return False

        # Time window check (handles midnight wrap)
        ingame = state.ingame_mins
        if w.get("use_time_window", False) and ingame is not None:
            start = w.get("window_start", "00:00")
            end   = w.get("window_end",   "23:59")
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
        executor.execute(Action("check_weapon_store", _task=self), state)
