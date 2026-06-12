"""
Performs fire duties when the action timer is ready.
Only runs when in home city and occupation is in the Fire career.
Always selects the last (highest tier) option.
"""

from tasks.base import Task, Action
from state import GameState
from action_cooldowns import ACTION_COOLDOWNS, should_skip_action_for_armed_robbery


class FireDutiesTask(Task):
    priority = 60
    label = 'Fire Duties'

    def can_run(self, state: GameState) -> bool:
        if not (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and "fire" in state.occupation.lower()
                and not state.hold_action_timer):
            return False
        return not should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["fire_duties"])

    def run(self, state: GameState, executor):
        executor.execute(Action("do_fire_duties"), state)
