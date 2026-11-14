"""
Black market check task — reads the local black market on a timer, and on
arrival in a new city, and uploads the prices to the Player Hub so every bot
can compare cities. Characters that can't see the market (redirected) are
retried after a 1 hour cooldown.
"""

import time

import black_market
import config as cfg
import war_hub_client
from tasks.base import Task, Action
from state import GameState

DEFAULT_INTERVAL_MIN = 15


def _bm_cfg() -> dict:
    return cfg.load().get("black_market", {})


class BlackMarketCheckTask(Task):
    priority = 5
    label = "Black Market Check"

    def __init__(self):
        self._last: float = 0.0
        self._last_city: str = ""

    def _interval(self) -> int:
        try:
            minutes = float(_bm_cfg().get("check_interval_min", DEFAULT_INTERVAL_MIN))
        except (TypeError, ValueError):
            minutes = DEFAULT_INTERVAL_MIN
        return int(max(1.0, minutes) * 60)

    def _due(self, state: GameState) -> bool:
        if (state.current_city or "") != self._last_city:
            return True  # just arrived somewhere new
        return time.monotonic() - self._last >= self._interval()

    def can_run(self, state: GameState) -> bool:
        if not _bm_cfg().get("check_enabled", True) or not war_hub_client.is_configured():
            return False
        if not state.logged_in or state.in_jail or state.in_hospital or not state.current_city:
            return False
        if black_market.unavailable_remaining():
            return False
        return self._due(state)

    def blocked_reasons(self, state):
        reasons = []
        if not _bm_cfg().get("check_enabled", True):
            reasons.append("Black market checks disabled")
        if not war_hub_client.is_configured():
            reasons.append("Player Hub not configured")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        left = black_market.unavailable_remaining()
        if left:
            reasons.append(f"Market not available ({left // 60 + 1}m)")
        if not self._due(state):
            reasons.append(f"Interval ({int(self._interval() - (time.monotonic() - self._last))}s)")
        return reasons

    def run(self, state: GameState, executor):
        self._last = time.monotonic()
        self._last_city = state.current_city or ""
        executor.execute(Action("check_black_market"), state)
