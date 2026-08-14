"""
Refreshes game state by navigating to the play page when the bot has been
idle for the configured interval. Lowest priority — only fires when nothing
else runs.
"""

import time
from tasks.base import Task, Action
from state import GameState


class RefreshTask(Task):
    priority = 1
    label = 'Refresh'
    run_in_hospital = True

    def __init__(self, interval_seconds: int = 60):
        self._interval = interval_seconds
        self._last_run: float = 0.0

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and (time.monotonic() - self._last_run) >= self._interval

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        remaining = self._interval - (time.monotonic() - self._last_run)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining)}s)")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("refresh_state"), state)
        self._last_run = time.monotonic()
