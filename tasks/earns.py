"""
Checks the earn queue on a timer and tops it up to 200 if below 50.
"""

import time
from tasks.base import Task, Action


class EarnsTask(Task):
    priority = 30
    label = 'Earns'

    def __init__(self, earn_type: str, interval_minutes: float = 30):
        self.earn_type = earn_type
        self._interval = interval_minutes * 60
        self._last_fired: float = 0.0

    def can_run(self, state) -> bool:
        return state.logged_in and not state.in_jail and time.monotonic() - self._last_fired >= self._interval

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        remaining = self._interval - (time.monotonic() - self._last_fired)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining // 60)}m left)")
        return reasons

    def run(self, state, executor):
        self._last_fired = time.monotonic()
        executor.execute(Action("check_earns", earn_type=self.earn_type), state)
