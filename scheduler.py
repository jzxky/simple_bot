"""
Priority-ordered task scheduler. Each tick, runs the first task whose
can_run() returns True.
"""

from tasks.base import Task


class Scheduler:
    def __init__(self):
        self._tasks: list[Task] = []

    def add(self, task: Task):
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: t.priority, reverse=True)

    def tick(self, state, executor):
        for task in self._tasks:
            if state.in_hospital and not task.run_in_hospital:
                continue
            if task.can_run(state):
                state.current_task = task.label or type(task).__name__
                try:
                    task.run(state, executor)
                finally:
                    state.current_task = ""
                return

    def snapshot(self, state) -> list[dict]:
        """Return current can_run status for all tasks without running any."""
        result = []
        for task in self._tasks:
            try:
                ready = task.can_run(state)
            except Exception:
                ready = False
            result.append({
                "label": task.label or type(task).__name__,
                "priority": task.priority,
                "ready": ready,
            })
        return result
