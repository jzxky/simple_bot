import config as cfg
from tasks.base import Task, Action
from state import GameState

_PRIORITY = ["porn", "booze", "cigarettes"]


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

    def blocked_reasons(self, state):
        reasons = []
        if not state.in_jail:
            reasons.append("Not in jail")
        if not state.logged_in:
            reasons.append("Not logged in")
        jail_cfg = cfg.load().get("jail", {})
        if not jail_cfg.get("enabled", False):
            reasons.append("Not enabled")
        if not jail_cfg.get("use_consumables", False):
            reasons.append("Consumables off")
        jcons = state.jail_consumables or {}
        if not any(jcons.get(c, 0) > 0 for c in _PRIORITY):
            reasons.append("No consumables")
        if not state.timers.get("case", {}).get("ready", False):
            reasons.append("Case timer not ready")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("jail_consume"), state)
