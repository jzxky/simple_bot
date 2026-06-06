"""
Priority-based, interruptible task scheduler.
"""

import time
from typing import Optional
from tasks.base import Task, Action


class Scheduler:
    def __init__(self, tick_interval: float = 1.0):
        self._tasks: list[Task] = []
        self._current: Optional[Task] = None
        self.tick_interval = tick_interval

    def add(self, task: Task):
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: t.priority, reverse=True)

    def remove(self, task: Task):
        if task is self._current:
            task.interrupt()
            self._current = None
        self._tasks = [t for t in self._tasks if t is not task]

    def _select(self, state) -> Optional[Task]:
        for task in self._tasks:
            if task.can_run(state):
                return task
        return None

    def tick(self, state, executor):
        best = self._select(state)
        if best is None:
            return

        if self._current is not None and self._current is not best:
            if best.priority > self._current.priority:
                self._current.interrupt()
                self._current = None

        if self._current is None or self._current is not best:
            best.resume()
            self._current = best

        action = best.run(state)

        if action is not None:
            executor.execute(action, state)

        if best.is_complete:
            self._current = None
            self._tasks = [t for t in self._tasks if not t.is_complete]

    def run_loop(self, state, executor, stop_flag):
        while not stop_flag():
            self.tick(state, executor)
            time.sleep(self.tick_interval)
