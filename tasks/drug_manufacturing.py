"""
Performs drug manufacturing when the action timer is ready.
Requires Gangster career and a science degree — redirects to income page otherwise.
"""

from tasks.base import Task, Action
from state import GameState


class DrugManufacturingTask(Task):
    priority = 60
    label = 'Drug Manufacturing'

    def can_run(self, state: GameState) -> bool:
        return (state.logged_in
                and not state.in_jail
                and state.action_available()
                and state.in_home_city()
                and "gangster" in state.occupation.lower()
                and not state.hold_action_timer)

    def run(self, state: GameState, executor):
        executor.execute(Action("do_drug_manufacturing"), state)
