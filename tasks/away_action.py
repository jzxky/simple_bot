"""
Performs the configured away-from-home-city action when the action timer is ready.
Supported types: drug_manufacturing, community_service, dog_trains.
"""

from tasks.base import Task, Action
from state import GameState


class AwayActionTask(Task):
    priority = 40
    label = 'Away Action'

    def __init__(self, action_type: str):
        self.action_type = action_type

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and state.action_available() and not state.in_home_city()

    def run(self, state: GameState, executor):
        if self.action_type == "community_service":
            executor.execute(Action("do_community_service", in_home_city=False), state)
        elif self.action_type == "drug_manufacturing":
            executor.execute(Action("do_drug_manufacturing"), state)
        elif self.action_type == "dog_trains":
            executor.execute(Action("do_dog_trains"), state)
        else:
            state.add_log(f"Unknown away action type: {self.action_type}")
