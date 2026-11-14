"""
Drug trade autobuy task — triggered by "Drug Trade Offer" journal entries.
Runs in the drug window (drug_window.py), not the main browser window.
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
        return (state.logged_in and not state.in_jail and not state.drug_tab_active
                and not self._queue.empty())

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.drug_tab_active:
            reasons.append("Drug window busy")
        if self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        try:
            self._queue.get_nowait()
        except Exception:
            return
        import drug_window
        drug_window.submit(state, Action("check_drug_trade"))
