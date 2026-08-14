import config as cfg
from tasks.base import Task, Action
from state import GameState


class JailActionTask(Task):
    priority = 60
    label = 'Jail Action'

    def can_run(self, state: GameState) -> bool:
        if not state.in_jail or not state.logged_in:
            return False
        if not cfg.load().get("jail", {}).get("enabled", False):
            return False
        return state.action_available()

    def blocked_reasons(self, state):
        reasons = []
        if not state.in_jail:
            reasons.append("Not in jail")
        if not state.logged_in:
            reasons.append("Not logged in")
        if not cfg.load().get("jail", {}).get("enabled", False):
            reasons.append("Not enabled")
        if not state.action_available():
            reasons.append("Action timer busy")
        return reasons

    def run(self, state: GameState, executor):
        action = cfg.load().get("jail", {}).get("action", "gym")
        executor.execute(Action("jail_action", action=action), state)
