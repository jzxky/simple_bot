"""
War Mode WS monitor task.

When War Mode is enabled, periodically sweeps the opps/friendlies watch lists,
visiting each profile and parsing whacks-survived. An increase over the stored
value marks the character as whacked (handled in war_mode.record_ws).
"""

import time

import config as cfg
import war_mode
from tasks.base import Task, Action
from state import GameState


class WSMonitorTask(Task):
    priority = 20
    label = "WS Monitor"

    def __init__(self):
        self._last: float = 0.0

    def _interval(self) -> int:
        m = cfg.load().get("war_mode", {}).get("monitor_interval_minutes", 5)
        return max(1, int(m or 5)) * 60

    def can_run(self, state: GameState) -> bool:
        if not cfg.load().get("war_mode", {}).get("enabled", False):
            return False
        if not state.logged_in or state.in_jail:
            return False
        if not war_mode.all_names():
            return False
        return time.monotonic() - self._last >= self._interval()

    def run(self, state: GameState, executor):
        self._last = time.monotonic()
        executor.execute(Action("ws_monitor"), state)
