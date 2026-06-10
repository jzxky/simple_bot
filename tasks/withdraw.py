import queue
from tasks.base import Task, Action
from state import GameState


class WithdrawTask(Task):
    priority = 30
    label = 'Withdraw'

    def __init__(self, withdraw_queue: queue.Queue):
        self._queue = withdraw_queue

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        return not self._queue.empty()

    def run(self, state: GameState, executor):
        try:
            amount = self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("withdraw", amount=amount), state)
