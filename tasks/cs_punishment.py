"""
Handles the community-service punishment that blocks aggravated crimes.

When the bot receives a "complete another N Services" message from agcrime.asp,
state.cs_sentence is set to N. This task then:
  - Probes agcrime.asp — if it loads without redirect, CS is no longer required
  - Otherwise performs community service (home or away city)
  - Probes agcrime.asp again — if it loads, clears cs_sentence and re-enables aggs

When outside the home city, the task checks the known rank/occupation list to
determine if away-city CS is available. If not, it auto-travels home.

Priority (61) is set above the action-timer tasks (agg crimes, gym, casino,
event boss, etc.) so a CS sentence is always served first.
AggCrimeTask.can_run also returns False when cs_sentence > 0.
"""

from tasks.base import Task, Action
from tasks.away_action import _CS_AWAY_ALLOWED_RANKS
from state import GameState


def _can_do_away_cs(state: GameState) -> bool:
    rank_lower = (state.rank or "").lower()
    occ_lower = (state.occupation or "").lower()
    return rank_lower in _CS_AWAY_ALLOWED_RANKS or occ_lower in _CS_AWAY_ALLOWED_RANKS


class CSPunishmentTask(Task):
    priority = 61
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
        if not state.in_home_city() and not _can_do_away_cs(state):
            from executor import travel_warrant_cooldown_active, no_vehicle_cooldown_active
            if not (state.timer_ready("travel") or "travel" not in state.timers):
                return False
            if travel_warrant_cooldown_active() or no_vehicle_cooldown_active():
                return False
        return True

    def blocked_reasons(self, state):
        reasons = []
        if state.cs_sentence <= 0:
            reasons.append("No CS sentence")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if not state.action_available():
            reasons.append("Action timer busy")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if not state.in_home_city() and not _can_do_away_cs(state):
            from executor import travel_warrant_cooldown_active, no_vehicle_cooldown_active
            if not (state.timer_ready("travel") or "travel" not in state.timers):
                reasons.append("Away CS unavailable — waiting for travel timer")
            if travel_warrant_cooldown_active():
                reasons.append("Away CS unavailable — warrant travel cooldown")
            if no_vehicle_cooldown_active():
                reasons.append("Away CS unavailable — no vehicle cooldown")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("probe_agcrime"), state)
        if state.cs_sentence <= 0:
            state.add_log("CS punishment: agcrime.asp loaded — no CS required. Re-enabling aggs.")
            return

        if state.in_home_city():
            executor.execute(Action("do_community_service", in_home_city=True), state)
        elif _can_do_away_cs(state):
            executor.execute(Action("do_community_service", in_home_city=False), state)
        else:
            state.add_log("CS punishment: away CS not available for this rank — travelling home.")
            executor.execute(Action("travel", target_city=state.home_city, method="own_vehicle"), state)
            return

        executor.execute(Action("probe_agcrime"), state)
        if state.cs_sentence <= 0:
            state.add_log("CS punishment complete — aggravated crimes re-enabled.")
        else:
            state.add_log(f"CS punishment: {state.cs_sentence} service(s) still required.")
