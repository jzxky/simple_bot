"""
Handles the community-service punishment that blocks aggravated crimes.

When the bot receives a "complete another N Services" message from agcrime.asp,
state.cs_sentence is set to N. This task then:
  - Probes agcrime.asp — if it loads without redirect, CS is no longer required
  - Otherwise performs community service
  - Probes agcrime.asp again — if it loads, clears cs_sentence and re-enables aggs

Priority is set above AggCrimeTask (50) so CS punishment is always preferred.
AggCrimeTask.can_run also returns False when cs_sentence > 0.
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
        if not state.in_home_city():
            return False
        return True

    def run(self, state: GameState, executor):
        # Verify CS is still required
        executor.execute(Action("probe_agcrime"), state)
        if state.cs_sentence <= 0:
            state.add_log("CS punishment: agcrime.asp loaded — no CS required. Re-enabling aggs.")
            return

        # Do community service
        executor.execute(Action("do_community_service", in_home_city=True), state)

        # Check if CS is now cleared
        executor.execute(Action("probe_agcrime"), state)
        if state.cs_sentence <= 0:
            state.add_log("CS punishment complete — aggravated crimes re-enabled.")
        else:
            state.add_log(f"CS punishment: {state.cs_sentence} service(s) still required.")
