"""
Works through all university degrees in sequence when the action timer is ready,
or studies a single configured degree.
"""

import config as cfg
import urls
from tasks.base import Task, Action
from state import GameState
from action_cooldowns import ACTION_COOLDOWNS, should_skip_action_for_armed_robbery

UNIVERSITY_PATH = "/localcity/university.asp"
DEGREES = ["Business", "Science", "Medicine", "Engineering", "Law"]


class UniversityTask(Task):
    priority = 60
    label = "University"

    def __init__(self, degree: str = ""):
        self.degree = degree  # empty = all degrees in order

    def can_run(self, state: GameState) -> bool:
        action_cfg = cfg.load().get("action", {})
        if not action_cfg.get("enabled", False):
            return False
        # A fallback may have switched the action type; don't run again in the
        # moment before the scheduler rebuilds without this task.
        if action_cfg.get("type") != "university":
            return False
        if not (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and not state.hold_action_timer):
            return False
        return not should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["university"])

    def blocked_reasons(self, state):
        reasons = []
        action_cfg = cfg.load().get("action", {})
        if not action_cfg.get("enabled", False):
            reasons.append("Not enabled")
        elif action_cfg.get("type") != "university":
            reasons.append("Action switched (fallback)")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if not state.action_available():
            reasons.append("Action timer busy")
        if not state.in_home_city():
            reasons.append("Not in home city")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["university"]):
            reasons.append("Waiting for armed robbery")
        return reasons

    def run(self, state: GameState, executor):
        url = urls.BASE_URL + UNIVERSITY_PATH
        executor.execute(Action("do_university", url=url, degree=self.degree), state)
