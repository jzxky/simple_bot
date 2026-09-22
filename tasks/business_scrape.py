"""
Business ownership scrape task.

Periodically visits /business/business.asp and reports business ownership
data to the Player Hub.
"""

import time

import config as cfg
from tasks.base import Task, Action
from state import GameState


class BusinessScrapeTask(Task):
    priority = 5
    label = "Business Scrape"

    def __init__(self):
        self._last: float = 0.0

    def can_run(self, state: GameState) -> bool:
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            return False
        if not state.logged_in:
            return False
        return time.monotonic() - self._last >= 35

    def blocked_reasons(self, state):
        reasons = []
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            reasons.append("War mode disabled")
        if not state.logged_in:
            reasons.append("Not logged in")
        remaining = 35 - (time.monotonic() - self._last)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining)}s)")
        return reasons

    def run(self, state: GameState, executor):
        self._last = time.monotonic()
        executor.execute(Action("scrape_businesses"), state)
