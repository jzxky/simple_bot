"""
Performs fire duties when the action timer is ready.
Only runs when in home city and occupation is in the Fire career.
Always selects the last (highest tier) option.
"""

from tasks.base import Task, Action
from state import GameState


class FireDutiesTask(Task):
    priority = 60
    label = 'Fire Duties'

    def can_run(self, state: GameState) -> bool:
        return (
            state.logged_in
            and not state.in_jail
            and state.action_available()
            and state.in_home_city()
            and "fire" in state.occupation.lower()
        )

    def run(self, state: GameState, executor):
        executor.execute(Action("do_fire_duties"), state)
