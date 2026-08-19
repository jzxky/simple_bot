"""
Bundles first-login housekeeping into a single scheduler tick:
earn catalog refresh, earn queue check, and player list refresh.
"""

import time
from tasks.base import Task, Action
from state import GameState


class StartupTask(Task):
    priority = 89
    label = "Startup Bundle"

    def __init__(self, earns_task=None, char_history_task=None, player_refresh_task=None):
        self._done = False
        self._earns_task = earns_task
        self._char_history_task = char_history_task
        self._player_refresh_task = player_refresh_task

    def can_run(self, state: GameState) -> bool:
        return not self._done and state.logged_in and not state.in_jail

    def blocked_reasons(self, state):
        reasons = []
        if self._done:
            reasons.append("Already completed")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        return reasons

    def run(self, state: GameState, executor):
        self._done = True

        state.add_log("Startup: refreshing earn catalog.")
        try:
            executor.execute(Action("refresh_earn_catalog"), state)
        except Exception as e:
            state.add_log(f"Startup earn catalog refresh failed: {e}")

        state.add_log("Startup: checking earn queue.")
        try:
            executor.execute(Action("check_earns"), state)
        except Exception as e:
            state.add_log(f"Startup earn queue check failed: {e}")

        state.add_log("Startup: refreshing player list.")
        try:
            from players import _refresh_impl
            count, marked = _refresh_impl()
            msg = f"Startup: player list refreshed: {count} active players."
            if marked:
                msg += f" Marked {marked} absent player(s) as dead."
            state.add_log(msg)
        except Exception as e:
            state.add_log(f"Startup player refresh failed: {e}")

        now = time.monotonic()
        if self._earns_task and hasattr(self._earns_task, "_last_fired"):
            self._earns_task._last_fired = now
        if self._char_history_task and hasattr(self._char_history_task, "_last_run"):
            self._char_history_task._last_run = time.time()
        if self._player_refresh_task and hasattr(self._player_refresh_task, "_last_run"):
            self._player_refresh_task._last_run = now
