"""
Works through all university degrees in sequence when the action timer is ready.
"""

import config as cfg
import urls
from tasks.base import Task, Action
from state import GameState
from action_cooldowns import ACTION_COOLDOWNS, should_skip_action_for_armed_robbery

UNIVERSITY_PATH = "/localcity/university.asp"
DEGREES = ["Law", "Science", "Business", "Engineering"]


class UniversityTask(Task):
    priority = 60
    label = "University"

    def can_run(self, state: GameState) -> bool:
        if not cfg.load().get("action", {}).get("enabled", False):
            return False
        if not (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and not state.hold_action_timer):
            return False
        return not should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["university"])

    def run(self, state: GameState, executor):
        url = urls.BASE_URL + UNIVERSITY_PATH
        executor.execute(Action("do_university", url=url), state)
