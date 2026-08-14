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
        import executor
        if executor.drug_manufacture_cooldown_active():
            return False
        return (state.logged_in
                and not state.in_jail
                and state.action_available()
                and state.in_home_city()
                and "gangster" in state.occupation.lower()
                and not state.hold_action_timer)

    def blocked_reasons(self, state):
        reasons = []
        import executor
        if executor.drug_manufacture_cooldown_active():
            reasons.append("Manufacture cooldown")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if not state.action_available():
            reasons.append("Action timer busy")
        if not state.in_home_city():
            reasons.append("Not in home city")
        if "gangster" not in state.occupation.lower():
            reasons.append("Not a gangster")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("do_drug_manufacturing"), state)
