"""
Performs career training when the action timer is ready.
"""

import urls
from tasks.base import Task, Action
from state import GameState

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
        return (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and not state.hold_action_timer)

    def run(self, state: GameState, executor):
        path = _CAREER_PATHS.get(self.career)
        if not path:
            state.add_log(f"Unknown career: {self.career}")
            return
        url = urls.BASE_URL + path
        executor.execute(Action("do_career_training", career=self.career, url=url), state)
