"""
Blind eye task — process the blind eye queue by selecting gangsters on the
blind eye page and submitting the form.
"""

import queue
from tasks.base import Task, Action
from state import GameState


class BlindEyeTask(Task):
    priority = 4
    label = "Blind Eye"

    def __init__(self, blind_eye_queue: queue.Queue):
        self._queue = blind_eye_queue

    def can_run(self, state: GameState) -> bool:
        return (
            state.logged_in
            and not state.in_jail
            and state.in_home_city()
            and state.timer_ready("traffick")
            and not self._queue.empty()
        )

    def run(self, state: GameState, executor):
        try:
            self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("do_blind_eye"), state)
