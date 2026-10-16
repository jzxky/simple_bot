"""
Earn planner — checks progress on the planner's active earn after each
character-history update and moves through the planner queue (see
earn_planner.py / executor.handle_earn_planner_check).

Only runs while the planner is enabled, has earns queued, and Character
History is enabled (the earn counts come from it). While waiting for an earn
to become available it rechecks every 10 minutes, silently.
"""

import time
import config as cfg
from tasks.base import Task, Action
from state import GameState

WAITING_RECHECK_SECS = 10 * 60


class EarnPlannerTask(Task):
    priority = 31   # just above the Earns task so a switch lands before its next top-up
    label = "Earn Planner"

    def __init__(self):
        # -inf = never checked, so the first waiting recheck is always due
        # (time.monotonic() can be small right after boot).
        self._last_wait_check: float = float("-inf")

    @staticmethod
    def _cfg():
        c = cfg.load()
        return c.get("earn_planner", {}), c.get("character_history", {})

    def _waiting_due(self, planner: dict) -> bool:
        return (planner.get("waiting_for_earns", False)
                and time.monotonic() - self._last_wait_check >= WAITING_RECHECK_SECS)

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        planner, history = self._cfg()
        if not (planner.get("enabled") and planner.get("limits") and history.get("enabled")):
            return False
        return state.earn_planner_check_pending or self._waiting_due(planner)

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        planner, history = self._cfg()
        if not planner.get("enabled"):
            reasons.append("Not enabled")
        elif not planner.get("limits"):
            reasons.append("No earns in planner")
        if not history.get("enabled"):
            reasons.append("Character History disabled")
        if planner.get("waiting_for_earns"):
            remaining = WAITING_RECHECK_SECS - (time.monotonic() - self._last_wait_check)
            if 0 < remaining < float("inf"):
                reasons.append(f"Waiting for an available earn ({int(remaining // 60)}m)")
        elif not state.earn_planner_check_pending:
            reasons.append("Waiting for next history update")
        return reasons

    def run(self, state: GameState, executor):
        planner, _ = self._cfg()
        state.earn_planner_check_pending = False
        if planner.get("waiting_for_earns"):
            self._last_wait_check = time.monotonic()
        executor.execute(Action("earn_planner_check"), state)
