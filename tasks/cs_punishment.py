"""
Handles the community-service punishment that blocks aggravated crimes.

When the bot receives a "complete another N Services" message from agcrime.asp,
state.cs_sentence is set to N. This task then:
  - Blocks until the action timer is ready and the character is in home city
  - Performs community service and increments state.cs_completed
  - Resets both counters once cs_completed reaches cs_sentence

Priority is set above AggCrimeTask (50) so CS punishment is always preferred
over attempting agg crimes while a sentence is active. AggCrimeTask.can_run
also returns False when cs_sentence > 0, ensuring the gangster stays idle
(and does not attempt aggs) while away from home city waiting to serve CS.
"""

from tasks.base import Task, Action
from state import GameState


class CSPunishmentTask(Task):
    priority = 55
    label = "CS Punishment"

    def can_run(self, state: GameState) -> bool:
        if state.cs_sentence <= 0:
            return False
        if not (state.logged_in and not state.in_jail and not state.in_hospital):
            return False
        if not state.action_available():
            return False
        if state.hold_action_timer:
            return False
        # Must be in home city to do community service
        if not state.in_home_city():
            return False
        return True

    def run(self, state: GameState, executor):
        executor.execute(Action("do_community_service", in_home_city=True), state)
        state.cs_completed += 1
        remaining = state.cs_sentence - state.cs_completed
        if remaining <= 0:
            state.add_log(
                f"CS punishment complete — served {state.cs_sentence} service(s). "
                "Aggravated crimes re-enabled."
            )
            state.cs_sentence = 0
            state.cs_completed = 0
        else:
            state.add_log(
                f"CS punishment: {state.cs_completed}/{state.cs_sentence} done, "
                f"{remaining} remaining."
            )
