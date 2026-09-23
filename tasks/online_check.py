"""
Online player list reporter for war mode (server mode).

Periodically reports the current city's online player list to the Player Hub.
"""

import time

import config as cfg
from tasks.base import Task
from state import GameState


class OnlineCheckTask(Task):
    priority = 6
    label = "Online Check"

    def __init__(self):
        self._last: float = 0.0

    def _is_server_mode(self) -> bool:
        c = cfg.load()
        wm = c.get("war_mode", {})
        sc = c.get("sync", {})
        return (wm.get("mode") == "server"
                and sc.get("enabled") and sc.get("server_url") and sc.get("api_key"))

    def _interval(self) -> int:
        wm = cfg.load().get("war_mode", {})
        return max(1, int(wm.get("online_check_interval_minutes", 1) or 1)) * 60

    def can_run(self, state: GameState) -> bool:
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            return False
        if not wm.get("checking_enabled", False):
            return False
        if not self._is_server_mode():
            return False
        if not state.logged_in:
            return False
        if not state.current_city:
            return False
        return time.monotonic() - self._last >= self._interval()

    def blocked_reasons(self, state):
        reasons = []
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            reasons.append("War mode disabled")
        if not wm.get("checking_enabled", False):
            reasons.append("Checking disabled")
        if not self._is_server_mode():
            reasons.append("Not in server mode")
        if not state.logged_in:
            reasons.append("Not logged in")
        if not state.current_city:
            reasons.append("No current city")
        remaining = self._interval() - (time.monotonic() - self._last)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining // 60)}m)")
        return reasons

    def run(self, state: GameState, executor):
        import war_hub_client
        self._last = time.monotonic()
        online = list(state.local_players)
        war_hub_client.report_online(state.current_city, online)
        state.add_log(f"Online check: reported {len(online)} player(s) in {state.current_city}.")
