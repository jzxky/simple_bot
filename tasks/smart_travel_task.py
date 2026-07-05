"""
Smart Travel task — when enabled and the travel timer is free, asks the smart
travel director which city to be in and issues the travel. Positions the bot;
the gym/casino/store tasks do the actual activity once it's in the right city.
"""

import time

import config as cfg
import smart_travel as director
from tasks.base import Task, Action
from state import GameState
from tasks.gym import load_last_gym_use
from tasks.casino import load_casino_release_at

_POLL_INTERVAL = 20  # seconds between director evaluations


def _travel_free(state: GameState) -> bool:
    # Treat a missing travel-timer entry as free (the game only shows it on cooldown).
    return ("travel" not in state.timers) or state.timer_ready("travel")


# config key → store label for logs
_STORES = {"bionics": "Bionics", "weapon_store": "Weapon Store"}


class SmartTravelTask(Task):
    priority = 45  # below gym (55)/casino (50) so activities run first when in-city
    label = "Smart Travel"

    def __init__(self):
        self._last: float = 0.0
        # Per-store signature (window_start, window_end) of the window last seen
        # active. Used to tell a genuine expiry (unchanged when it passes) from a
        # restock renewal (window moved to new times).
        self._win_sig = {"bionics": None, "weapon_store": None}

    def can_run(self, state: GameState) -> bool:
        # Runs regardless of the travel timer so it can also manage store windows;
        # actual travel is only issued when the timer is free (checked in run()).
        if not cfg.load().get("smart_travel", {}).get("enabled", False):
            return False
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.hold_action_timer:
            return False
        return time.monotonic() - self._last >= _POLL_INTERVAL

    def _build_ctx(self, state: GameState, c: dict) -> dict:
        return {
            "now_ts": time.time(),
            "ingame_mins": state.ingame_mins,
            "current_city": state.current_city or "",
            "home_city": state.home_city or "",
            "smart": c.get("smart_travel", {}),
            "bionics": c.get("bionics", {}),
            "weapon": c.get("weapon_store", {}),
            "gym": c.get("gym", {}),
            "casino": c.get("casino", {}),
            "last_gym_use": load_last_gym_use(),
            "casino_release_at": load_casino_release_at(),
        }

    def _manage_windows(self, state: GameState):
        """Phase 3: while a store window is set → 5-min interval; once it passes with
        no new window → disable the window check and drop to a 16-min interval."""
        c = cfg.load()
        smart = c.get("smart_travel", {})
        window_interval = max(1, int(smart.get("window_interval_minutes", 5) or 5))
        no_window_interval = max(1, int(smart.get("no_window_interval_minutes", 16) or 16))
        changed = False
        for key in ("bionics", "weapon_store"):
            store = c.get(key, {})
            if not store.get("enabled", False):
                continue
            if store.get("use_time_window", False):
                # A window is set — check frequently.
                if int(store.get("check_interval_minutes", 5)) != window_interval:
                    store["check_interval_minutes"] = window_interval
                    changed = True
                sig = (store.get("window_start", ""), store.get("window_end", ""))
                active = director.window_active(store, state.ingame_mins)
                if active:
                    # Remember the exact window we're covering.
                    self._win_sig[key] = sig
                elif self._win_sig[key] is not None:
                    if sig == self._win_sig[key]:
                        # Same window we covered has now passed and nothing renewed
                        # it (a restock would have changed window_start/end) → turn off.
                        store["use_time_window"] = False
                        store["check_interval_minutes"] = no_window_interval
                        self._win_sig[key] = None
                        changed = True
                        state.add_log(f"{_STORES[key]}: buy window passed with no restock — "
                                      f"window check off, interval → {no_window_interval}m.")
                    else:
                        # A restock moved the window — keep the toggle on and start
                        # tracking the new window afresh.
                        self._win_sig[key] = None
            else:
                self._win_sig[key] = None
        if changed:
            cfg.save(c)

    def run(self, state: GameState, executor):
        self._last = time.monotonic()
        self._manage_windows(state)

        if not _travel_free(state):
            return
        c = cfg.load()
        plan = director.decide_target_city(self._build_ctx(state, c))
        if plan.get("stay") or not plan.get("target"):
            return
        state.add_log(f"Smart travel: {plan['reason']} → travelling to {plan['target']}.")
        executor.execute(Action("travel", target_city=plan["target"], method="own_vehicle"), state)
