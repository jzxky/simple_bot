import config as cfg
from tasks.base import Task, Action
from state import GameState

_PRIORITY = ["porn", "booze", "cigarettes", "heroin"]


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
        jcons = state.jail_consumables or {}
        if not any(jcons.get(c, 0) > 0 for c in _PRIORITY):
            return False
        return state.timers.get("case", {}).get("ready", False)

    def run(self, state: GameState, executor):
        executor.execute(Action("jail_consume"), state)
