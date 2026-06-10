import queue
import config as cfg
from tasks.base import Task, Action
from state import GameState


class DepositTask(Task):
    priority = 50
    label = 'Deposit'

    def __init__(self, deposit_queue: queue.Queue):
        self._queue = deposit_queue

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        return not self._queue.empty()

    def run(self, state: GameState, executor):
        try:
            self._queue.get_nowait()
        except Exception:
            return
        min_cash = int(cfg.load().get("misc", {}).get("min_cash_on_hand", 0))
        executor.execute(Action("deposit", min_cash_on_hand=min_cash), state)
