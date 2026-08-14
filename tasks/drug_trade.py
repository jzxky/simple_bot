"""
Drug trade autobuy task — triggered by "Drug Trade Offer" journal entries.
"""

import queue
from tasks.base import Task, Action
from state import GameState


class DrugTradeTask(Task):
    priority = 4  # higher than journal check (5) so it runs first after journal triggers it
    label = "Drug Trade"

    def __init__(self, trade_queue: queue.Queue):
        self._queue = trade_queue

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
        executor.execute(Action("check_drug_trade"), state)
