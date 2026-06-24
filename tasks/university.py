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
DEGREES = ["Business", "Science", "Medical", "Engineering", "Law"]


class UniversityTask(Task):
    priority = 60
    label = "University"

    def __init__(self, degree: str = ""):
        self.degree = degree  # empty = all degrees in order

    def can_run(self, state: GameState) -> bool:
        if not cfg.load().get("action", {}).get("enabled", False):
            return False
        if not (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and not state.hold_action_timer):
            return False
        return not should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["university"])

    def run(self, state: GameState, executor):
        url = urls.BASE_URL + UNIVERSITY_PATH
        executor.execute(Action("do_university", url=url, degree=self.degree), state)
