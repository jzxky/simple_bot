"""
Performs community service when the action timer is ready.
Always selects the last (highest tier) option when in home city.
"""

from tasks.base import EventDrivenTask, Action
from state import GameState

CS_URL = "https://mafiamatrix.com/income/communityservice.asp"


class CommunityServiceTask(EventDrivenTask):
    def __init__(self):
        super().__init__(priority=40)

    def condition(self, state: GameState) -> bool:
        return state.logged_in and state.action_available()

    def run(self, state: GameState):
        self.is_complete = True  # one-shot per timer cycle; scheduler resets
        return Action("do_community_service", in_home_city=state.in_home_city())
