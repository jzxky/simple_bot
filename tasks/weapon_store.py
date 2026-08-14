"""
Checks the Auckland weapon store for wanted items and purchases them.

Runs when: logged in, not in jail/hospital, in Auckland, enabled in config,
enough wall-clock time has passed since last check, and (if use_time_window)
in-game time is within the configured window.

Purchase order follows config priority_order; if empty, uses store appearance order
for wanted items.
"""

import time
import store_windows
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
        self.last_checked_ingame: "int | None" = s.get("last_checked_ingame")
        self.last_stock: dict = s.get("last_stock", {})
        self.last_views: "tuple[int,int] | None" = None
        self._covered_sig: "str | None" = s.get("window_sig")

    def can_run(self, state: GameState) -> bool:
        import config as cfg
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.current_city.lower() != "auckland":
            return False
        w = cfg.load().get("weapon_store", {})
        if not w.get("enabled", False):
            return False

        # Wake on the window/no-window interval. When the toggle is on but we're
        # outside the window, run() still fires so it can detect the window
        # passing — it just won't visit the shop.
        interval_secs = store_windows.interval_secs(w, state.ingame_mins)
        if self.last_checked_at > 0 and time.time() - self.last_checked_at < interval_secs:
            return False
        return True

    def blocked_reasons(self, state):
        import config as cfg
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.current_city.lower() != "auckland":
            reasons.append("Not in Auckland")
        w = cfg.load().get("weapon_store", {})
        if not w.get("enabled", False):
            reasons.append("Not enabled")
        else:
            interval_secs = store_windows.interval_secs(w, state.ingame_mins)
            if self.last_checked_at > 0:
                remaining = interval_secs - (time.time() - self.last_checked_at)
                if remaining > 0:
                    reasons.append(f"Interval ({int(remaining)}s)")
        return reasons

    def _manage_window(self, state: GameState):
        """Auto-disable 'check during window only' once the covered window passes
        with no restock renewing it (restock moves window_start/end)."""
        import config as cfg
        c = cfg.load()
        w = c.get("weapon_store", {})
        if not w.get("use_time_window", False):
            if self._covered_sig is not None:
                self._covered_sig = None
                save_weapon_store_state({"window_sig": None})
            return
        if state.ingame_mins is None:
            return
        sig = store_windows.window_sig(w)
        if store_windows.in_window(w, state.ingame_mins):
            if self._covered_sig != sig:
                self._covered_sig = sig
                save_weapon_store_state({"window_sig": sig})
            return
        # Outside the window now.
        if self._covered_sig is None:
            return  # never observed this window active — stay conservative
        if sig == self._covered_sig:
            c["weapon_store"]["use_time_window"] = False
            cfg.save(c)
            import settings_rev
            settings_rev.bump()
            self._covered_sig = None
            save_weapon_store_state({"window_sig": None})
            state.add_log("Weapon Store: buy window passed with no restock — "
                          "'check during window only' turned off.")
        else:
            self._covered_sig = None
            save_weapon_store_state({"window_sig": None})

    def run(self, state: GameState, executor):
        import config as cfg
        self._manage_window(state)
        w = cfg.load().get("weapon_store", {})
        if w.get("use_time_window", False) and not store_windows.in_window(w, state.ingame_mins):
            self.last_checked_at = time.time()
            save_weapon_store_state({"last_checked_at": self.last_checked_at})
            return
        executor.execute(Action("check_weapon_store", _task=self), state)
