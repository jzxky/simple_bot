"""
Performs career training when the action timer is ready.
Supports fire, customs, and police.
"""

from tasks.base import EventDrivenTask, Action
from state import GameState

CAREER_URLS = {
    "fire": "https://mafiamatrix.com/localcity/fire.asp",
    "customs": "https://mafiamatrix.com/localcity/customs.asp",
    "police": "https://mafiamatrix.com/localcity/policerecruit.asp",
}


class CareerTrainingTask(EventDrivenTask):
    def __init__(self, career: str):
        super().__init__(priority=40)
        self.career = career

    def condition(self, state: GameState) -> bool:
        return state.logged_in and state.action_available()

    def run(self, state: GameState):
        self.is_complete = True
        url = CAREER_URLS.get(self.career)
        if not url:
            state.add_log(f"Unknown career: {self.career}")
            return None
        return Action("do_career_training", career=self.career, url=url)
