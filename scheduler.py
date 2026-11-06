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
        # Why a task isn't running is shown in the Scheduler panel
        # (snapshot()), so per-tick skip/blocked lines aren't logged here.
        for task in self._tasks:
            if state.in_hospital and not task.run_in_hospital:
                continue
            if state.agg_tab_active and task.changes_city:
                continue
            if task.can_run(state):
                state.current_task = task.label or type(task).__name__
                try:
                    task.run(state, executor)
                finally:
                    state.current_task = ""
                return

    def snapshot(self, state) -> list[dict]:
        """Return current can_run status and blocking reasons for all tasks."""
        result = []
        for task in self._tasks:
            reasons = []
            if state.in_hospital and not task.run_in_hospital:
                reasons.append("In hospital")
            if state.agg_tab_active and task.changes_city:
                reasons.append("Crime tab active")
            try:
                reasons.extend(task.blocked_reasons(state))
            except Exception:
                reasons.append("Error checking guards")
            ready = len(reasons) == 0
            result.append({
                "label": task.label or type(task).__name__,
                "priority": task.priority,
                "ready": ready,
                "reasons": reasons,
            })
        return result
