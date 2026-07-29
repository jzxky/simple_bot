"""
Manual earn mode — clicks Work one at a time whenever the earn timer is ready.
"""

from tasks.base import Task, Action


class ManualEarnsTask(Task):
    priority = 30
    label = 'Earns (Manual)'

    def __init__(self, earn_type: str):
        self.earn_type = earn_type

    def can_run(self, state) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        return state.timer_ready("earn")

    def run(self, state, executor):
        executor.execute(Action("manual_earn", earn_type=self.earn_type), state)
