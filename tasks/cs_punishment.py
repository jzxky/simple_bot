"""
Handles the community-service punishment that blocks aggravated crimes.

When the bot receives a "complete another N Services" message from agcrime.asp,
state.cs_sentence is set to N. This task then:
  - Probes agcrime.asp — if it loads without redirect, CS is no longer required
  - Otherwise performs community service (home or away city)
  - Probes agcrime.asp again — if it loads, clears cs_sentence and re-enables aggs

When outside the home city, the task visits the CS page to check for away-city
options. If none exist, it triggers a travel home. The "away unavailable" result
is cached by (rank, occupation) so repeated checks are avoided until either
changes.

Priority (61) is set above the action-timer tasks (agg crimes, gym, casino,
event boss, etc.) so a CS sentence is always served first.
AggCrimeTask.can_run also returns False when cs_sentence > 0.
"""

import browser
from bs4 import BeautifulSoup
from tasks.base import Task, Action
from state import GameState


_cs_away_unavailable_key: tuple = ()


def _away_cs_key(state: GameState) -> tuple:
    return ((state.rank or "").lower(), (state.occupation or "").lower())


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
        if not state.in_home_city():
            if _cs_away_unavailable_key and _cs_away_unavailable_key == _away_cs_key(state):
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
        if not state.in_home_city():
            if _cs_away_unavailable_key and _cs_away_unavailable_key == _away_cs_key(state):
                from executor import travel_warrant_cooldown_active, no_vehicle_cooldown_active
                if not (state.timer_ready("travel") or "travel" not in state.timers):
                    reasons.append("Away CS unavailable — waiting for travel timer")
                if travel_warrant_cooldown_active():
                    reasons.append("Away CS unavailable — warrant travel cooldown")
                if no_vehicle_cooldown_active():
                    reasons.append("Away CS unavailable — no vehicle cooldown")
        return reasons

    def run(self, state: GameState, executor):
        global _cs_away_unavailable_key

        executor.execute(Action("probe_agcrime"), state)
        if state.cs_sentence <= 0:
            state.add_log("CS punishment: agcrime.asp loaded — no CS required. Re-enabling aggs.")
            _cs_away_unavailable_key = ()
            return

        if state.in_home_city():
            executor.execute(Action("do_community_service", in_home_city=True), state)
        else:
            key = _away_cs_key(state)
            if _cs_away_unavailable_key == key:
                state.add_log("CS punishment: away CS unavailable — travelling home.")
                executor.execute(Action("travel", target_city=state.home_city, method="own_vehicle"), state)
                return
            if self._probe_away_cs(state):
                executor.execute(Action("do_community_service", in_home_city=False), state)
            else:
                _cs_away_unavailable_key = key
                state.add_log(f"CS punishment: no away CS options for {state.rank}/{state.occupation} — travelling home.")
                executor.execute(Action("travel", target_city=state.home_city, method="own_vehicle"), state)
                return

        executor.execute(Action("probe_agcrime"), state)
        if state.cs_sentence <= 0:
            state.add_log("CS punishment complete — aggravated crimes re-enabled.")
            _cs_away_unavailable_key = ()
        else:
            state.add_log(f"CS punishment: {state.cs_sentence} service(s) still required.")

    def _probe_away_cs(self, state: GameState) -> bool:
        """Visit the CS page and check if away-city options exist."""
        import urls
        try:
            page = browser.page()
            page.goto(urls.BASE_URL + "/income/communityservice.asp",
                      wait_until="domcontentloaded", timeout=15000)
            soup = BeautifulSoup(page.content(), "html.parser")
            options = soup.find_all("input", attrs={"name": "csinothercities", "type": "radio"})
            return len(options) > 0
        except Exception as e:
            state.add_log(f"CS punishment: probe away CS error: {e}")
            return False
