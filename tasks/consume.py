from tasks.base import Task, Action
from state import GameState
import queue


class ConsumeTask(Task):
    priority = 30

    def __init__(self, consume_queue: queue.Queue):
        self._queue = consume_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not self._queue.empty()

    def run(self, state: GameState, executor):
        try:
            consume_type = self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("consume", type=consume_type), state)
