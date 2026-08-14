"""
Launders dirty money through contacts when outside the home city and the
launder timer is available.
"""

from tasks.base import Task, Action
from state import GameState


class LaunderMoneyTask(Task):
    priority = 45
    label = 'Laundering'

    def __init__(self, launder_amount: int, preferred_contacts: list):
        self.launder_amount = launder_amount
        self.preferred_contacts = preferred_contacts

    def can_run(self, state: GameState) -> bool:
        if not (state.logged_in and not state.in_jail
                and not state.in_home_city() and state.dirty_money >= 5):
            return False
        if "launder" in state.timers and not state.timer_ready("launder"):
            return False
        import executor
        if executor.launder_cooldown_active(state.current_city):
            return False
        return True

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_home_city():
            reasons.append("In home city")
        if state.dirty_money < 5:
            reasons.append("Not enough dirty money")
        if "launder" in state.timers and not state.timer_ready("launder"):
            reasons.append("Launder timer not ready")
        import executor
        if executor.launder_cooldown_active(state.current_city):
            reasons.append("Launder cooldown")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("launder_money",
                                launder_amount=self.launder_amount,
                                preferred_contacts=self.preferred_contacts), state)
