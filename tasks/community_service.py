"""
Performs community service when the action timer is ready.
Always selects the last (highest tier) option when in home city.
"""

from tasks.base import Task, Action
from state import GameState
from action_cooldowns import ACTION_COOLDOWNS, should_skip_action_for_armed_robbery


class CommunityServiceTask(Task):
    priority = 60
    label = 'Community Service'

    def can_run(self, state: GameState) -> bool:
        if not (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and not state.hold_action_timer):
            return False
        return not should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["community_service"])

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if not state.action_available():
            reasons.append("Action timer busy")
        if not state.in_home_city():
            reasons.append("Not in home city")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["community_service"]):
            reasons.append("Waiting for armed robbery")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("do_community_service", in_home_city=state.in_home_city()), state)
