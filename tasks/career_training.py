"""
Performs career training when the action timer is ready.
"""

from tasks.base import Task, Action
from state import GameState

CAREER_URLS = {
    "fire":    "https://mafiamatrix.com/localcity/fire.asp",
    "customs": "https://mafiamatrix.com/localcity/customs.asp",
    "police":  "https://mafiamatrix.com/localcity/policerecruit.asp",
}


class CareerTrainingTask(Task):
    priority = 40

    def __init__(self, career: str):
        self.career = career

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and state.action_available()

    def run(self, state: GameState, executor):
        url = CAREER_URLS.get(self.career)
        if not url:
            state.add_log(f"Unknown career: {self.career}")
            return
        executor.execute(Action("do_career_training", career=self.career, url=url), state)
