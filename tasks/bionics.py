"""
Checks the Chicago bionics store for wanted items and purchases them.

Runs when: logged in, not in jail/hospital, in Chicago, enabled in config,
enough wall-clock time has passed since last check, and (if use_time_window)
in-game time is within the configured window.

Purchase order: heart → brain → eyes → legs → arms (most expensive first).
Withdraws cash before each navigation to the store.
"""

import time
import store_windows
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
        self.last_checked_ingame: "int | None" = s.get("last_checked_ingame")
        self.last_stock: dict       = s.get("last_stock", {})
        self.last_views: "tuple[int,int] | None" = None
        # Signature of the window we're actively covering; persisted so a restart
        # doesn't lose it (used to auto-disable the toggle when the window passes).
        self._covered_sig: "str | None" = s.get("window_sig")

    def can_run(self, state: GameState) -> bool:
        import config as cfg
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.current_city.lower() != "chicago":
            return False
        b = cfg.load().get("bionics", {})
        if not b.get("enabled", False):
            return False

        # Wake on the window/no-window interval. When the toggle is on but we're
        # outside the window, run() still fires (no-window cadence) so it can
        # detect the window passing — it just won't visit the shop.
        interval_secs = store_windows.interval_secs(b, state.ingame_mins)
        if self.last_checked_at > 0 and time.time() - self.last_checked_at < interval_secs:
            return False
        return True

    def _manage_window(self, state: GameState):
        """Auto-disable 'check during window only' once the covered window passes
        with no restock renewing it (restock moves window_start/end)."""
        import config as cfg
        c = cfg.load()
        b = c.get("bionics", {})
        if not b.get("use_time_window", False):
            if self._covered_sig is not None:
                self._covered_sig = None
                save_bionics_state({"window_sig": None})
            return
        if state.ingame_mins is None:
            return
        sig = store_windows.window_sig(b)
        if store_windows.in_window(b, state.ingame_mins):
            if self._covered_sig != sig:
                self._covered_sig = sig
                save_bionics_state({"window_sig": sig})
            return
        # Outside the window now.
        if self._covered_sig is None:
            return  # never observed this window active — stay conservative
        if sig == self._covered_sig:
            c["bionics"]["use_time_window"] = False
            cfg.save(c)
            import settings_rev
            settings_rev.bump()
            self._covered_sig = None
            save_bionics_state({"window_sig": None})
            state.add_log("Bionics: buy window passed with no restock — "
                          "'check during window only' turned off.")
        else:
            # Window moved (restock) before we re-covered it — retrack.
            self._covered_sig = None
            save_bionics_state({"window_sig": None})

    def run(self, state: GameState, executor):
        import config as cfg
        self._manage_window(state)
        b = cfg.load().get("bionics", {})
        # When window-only is on but we're outside the window, don't visit the
        # shop — just record the tick (management already ran above).
        if b.get("use_time_window", False) and not store_windows.in_window(b, state.ingame_mins):
            self.last_checked_at = time.time()
            save_bionics_state({"last_checked_at": self.last_checked_at})
            return
        executor.execute(Action("check_bionics", _task=self), state)
