"""
Black market sell task — after arriving in a city, sells goods bought
elsewhere once they clear the minimum profit. Waits for the trafficking
timer, and tries each city at most once per check interval.
"""

import time

import black_market
import black_market_trade as bmt
import war_hub_client
from tasks.base import Task, Action
from tasks.black_market_check import _bm_cfg, DEFAULT_INTERVAL_MIN
from state import GameState


def _traffick_free(state: GameState) -> bool:
    return "traffick" not in state.timers or state.timer_ready("traffick")


class BlackMarketSellTask(Task):
    priority = 6  # ahead of the price check (5) so a fresh arrival sells first
    label = "Black Market Sell"

    def __init__(self):
        self._last: float = 0.0
        self._last_city: str = ""

    def _interval(self) -> int:
        try:
            minutes = float(_bm_cfg().get("check_interval_min", DEFAULT_INTERVAL_MIN))
        except (TypeError, ValueError):
            minutes = DEFAULT_INTERVAL_MIN
        return int(max(1.0, minutes) * 60)

    def _sellable(self, state: GameState) -> bool:
        """Holds goods bought in another city."""
        city = (state.current_city or "").lower()
        return any((lot.get("city") or "").lower() != city for lot in bmt.load()["lots"].values())

    def _due(self, state: GameState) -> bool:
        if (state.current_city or "") != self._last_city:
            return True
        return time.monotonic() - self._last >= self._interval()

    def can_run(self, state: GameState) -> bool:
        if not bmt.settings()["trading_enabled"] or not war_hub_client.is_configured():
            return False
        if not state.logged_in or state.in_jail or state.in_hospital or not state.current_city:
            return False
        if black_market.unavailable_remaining() or not _traffick_free(state):
            return False
        return self._due(state) and self._sellable(state)

    def blocked_reasons(self, state):
        reasons = []
        if not bmt.settings()["trading_enabled"]:
            reasons.append("Black market trading disabled")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if not _traffick_free(state):
            reasons.append("Trafficking timer not ready")
        if not self._sellable(state):
            reasons.append("Nothing held from another city")
        if not self._due(state):
            reasons.append(f"Interval ({int(self._interval() - (time.monotonic() - self._last))}s)")
        return reasons

    def run(self, state: GameState, executor):
        self._last = time.monotonic()
        self._last_city = state.current_city or ""
        executor.execute(Action("black_market_sell"), state)
