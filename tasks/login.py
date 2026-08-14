"""
Handles initial login and automatic session re-login.
"""

import time
import config as cfg
from tasks.base import Task, Action

RETRY_INTERVAL = 15


class LoginTask(Task):
    priority = 100
    label = 'Logging in'
    run_in_hospital = True

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self._last_attempt: float = 0.0

    def can_run(self, state) -> bool:
        return not state.logged_in and not state.relog_suppressed and time.monotonic() - self._last_attempt >= RETRY_INTERVAL

    def blocked_reasons(self, state):
        reasons = []
        if state.logged_in:
            reasons.append("Already logged in")
        if state.relog_suppressed:
            reasons.append("Relog suppressed")
        remaining = RETRY_INTERVAL - (time.monotonic() - self._last_attempt)
        if remaining > 0:
            reasons.append(f"Retry cooldown ({int(remaining)}s)")
        return reasons

    def run(self, state, executor):
        self._last_attempt = time.monotonic()
        executor.execute(Action("login", email=self.email, password=self.password), state)

        # On a successful login, grab the current event-consumable inventory so
        # it's known before any attack/consume cycle.
        if state.logged_in and cfg.load().get("event_boss", {}).get("enabled", False):
            executor.execute(Action("refresh_event_inventory"), state)
