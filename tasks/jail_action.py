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

    def run(self, state: GameState, executor):
        action = cfg.load().get("jail", {}).get("action", "gym")
        executor.execute(Action("jail_action", action=action), state)
