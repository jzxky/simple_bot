"""
Performs community service when the action timer is ready.
Always selects the last (highest tier) option when in home city.
"""

from tasks.base import Task, Action
from state import GameState


class CommunityServiceTask(Task):
    priority = 40

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and state.action_available() and state.in_home_city()

    def run(self, state: GameState, executor):
        executor.execute(Action("do_community_service", in_home_city=state.in_home_city()), state)
