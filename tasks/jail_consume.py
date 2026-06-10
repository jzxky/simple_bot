import config as cfg
from tasks.base import Task, Action
from state import GameState


class JailConsumeTask(Task):
    priority = 30
    label = 'Jail Consume'

    def can_run(self, state: GameState) -> bool:
        if not state.in_jail or not state.logged_in:
            return False
        jail_cfg = cfg.load().get("jail", {})
        if not jail_cfg.get("enabled", False):
            return False
        if not jail_cfg.get("use_consumables", False):
            return False
        consumable = jail_cfg.get("consumable", "cigarettes")
        if state.jail_consumables.get(consumable, 0) <= 0:
            return False
        return state.timers.get("case", {}).get("ready", False)

    def run(self, state: GameState, executor):
        consumable = cfg.load().get("jail", {}).get("consumable", "cigarettes")
        executor.execute(Action("jail_consume", consumable=consumable), state)
