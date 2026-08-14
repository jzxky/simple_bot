"""
Illness task — triggered by "Illness" journal entries containing the flu text.
"""

import queue
from tasks.base import Task, Action
from state import GameState


_FLU_TEXT = "you have a slightly nauseous feeling in your stomach"


class IllnessTask(Task):
    priority = 4
    label = "Illness"

    def __init__(self, illness_queue: queue.Queue):
        self._queue = illness_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not state.in_jail and not self._queue.empty()

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        try:
            self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("apply_illness_treatment"), state)
