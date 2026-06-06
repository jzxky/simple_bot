"""
Handles initial login and automatic session re-login.
"""

import time
from tasks.base import Task, Action
from state import GameState

RETRY_INTERVAL = 15  # seconds between login attempts


class LoginTask(Task):
    def __init__(self, email: str, password: str):
        super().__init__(priority=100)
        self.email = email
        self.password = password
        self._last_attempt: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if state.logged_in:
            return False
        return time.monotonic() - self._last_attempt >= RETRY_INTERVAL

    def run(self, state: GameState):
        self._last_attempt = time.monotonic()
        return Action("login", email=self.email, password=self.password)
