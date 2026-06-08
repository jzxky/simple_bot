"""
Performs drug manufacturing when the action timer is ready.
Requires Gangster career and a science degree — redirects to income page otherwise.
"""

from tasks.base import Task, Action
from state import GameState


class DrugManufacturingTask(Task):
    priority = 40

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and state.action_available() and state.in_home_city()

    def run(self, state: GameState, executor):
        executor.execute(Action("do_drug_manufacturing"), state)
