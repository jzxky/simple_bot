"""
Performs career training when the action timer is ready.
"""

import config as cfg
import urls
from tasks.base import Task, Action
from state import GameState
from action_cooldowns import ACTION_COOLDOWNS, should_skip_action_for_armed_robbery

_BLOCKED_OCCUPATIONS = {
    "customs", "volunteer fire fighter", "fire fighter", "fire chief", "police officer",
}

_CAREER_PATHS = {
    "fire":    "/localcity/fire.asp",
    "customs": "/localcity/customs.asp",
    "police":  "/localcity/policerecruit.asp",
}


class CareerTrainingTask(Task):
    priority = 60
    label = 'Career Training'

    def __init__(self, career: str):
        self.career = career

    def can_run(self, state: GameState) -> bool:
        if not cfg.load().get("action", {}).get("enabled", False):
            return False
        if not (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and not state.hold_action_timer):
            return False
        if (state.occupation or "").lower() in _BLOCKED_OCCUPATIONS:
            return False
        return not should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["career_training"])

    def run(self, state: GameState, executor):
        path = _CAREER_PATHS.get(self.career)
        if not path:
            state.add_log(f"Unknown career: {self.career}")
            return
        url = urls.BASE_URL + path
        executor.execute(Action("do_career_training", career=self.career, url=url), state)
