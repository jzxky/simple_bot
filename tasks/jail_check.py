"""
Jail check task for war mode (server mode).

Periodically visits jail.asp and reports inmates to the Player Hub.
Uses the same jail page parsing as the offline jailbreak target checker.
"""

import time

import config as cfg
from tasks.base import Task, Action
from state import GameState


class JailCheckTask(Task):
    priority = 7
    label = "Jail Check"

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
        return max(1, int(wm.get("jail_check_interval_minutes", 5) or 5)) * 60

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
        remaining = self._interval() - (time.monotonic() - self._last)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining // 60)}m)")
        return reasons

    def run(self, state: GameState, executor):
        self._last = time.monotonic()
        executor.execute(Action("check_jail"), state)
