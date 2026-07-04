"""
Dog Trains as a home action — runs through the community service page when the
action timer is ready and the bot is in its home city.
"""

from tasks.base import Task, Action
from state import GameState
from action_cooldowns import ACTION_COOLDOWNS, should_skip_action_for_armed_robbery


class DogTrainsTask(Task):
    priority = 60
    label = 'Dog Trains'

    def can_run(self, state: GameState) -> bool:
        if not (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and not state.hold_action_timer):
            return False
        return not should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS.get("dog_trains", 5))

    def run(self, state: GameState, executor):
        executor.execute(Action("do_dog_trains", context="home"), state)
