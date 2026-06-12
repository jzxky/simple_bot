"""
Handles initial login and automatic session re-login.
"""

import time
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

    def run(self, state, executor):
        self._last_attempt = time.monotonic()
        executor.execute(Action("login", email=self.email, password=self.password), state)
