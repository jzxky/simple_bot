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


class SmartTravelTask(Task):
    priority = 45  # below gym (55)/casino (50) so activities run first when in-city
    label = "Smart Travel"

    def __init__(self):
        self._last: float = 0.0

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

    def run(self, state: GameState, executor):
        self._last = time.monotonic()

        if not _travel_free(state):
            return
        c = cfg.load()
        plan = director.decide_target_city(self._build_ctx(state, c))
        if plan.get("stay") or not plan.get("target"):
            return
        state.add_log(f"Smart travel: {plan['reason']} → travelling to {plan['target']}.")
        executor.execute(Action("travel", target_city=plan["target"], method="own_vehicle"), state)
