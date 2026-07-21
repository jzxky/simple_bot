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
        if executor.launder_cooldown_active():
            return False
        return True

    def run(self, state: GameState, executor):
        executor.execute(Action("launder_money",
                                launder_amount=self.launder_amount,
                                preferred_contacts=self.preferred_contacts), state)
