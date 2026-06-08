"""
Aggravated crime task.

Primary crime is always attempted when in home city (or for non-home-city crimes, anywhere).
Away crime is only configured when primary is 'hack' and is attempted when not in home city.
A 3-minute cooldown applies after all targets are exhausted.
"""

import time
from tasks.base import Task, Action
from state import GameState

HACK_CRIME = "hack"
COOLDOWN_SECONDS = 180


class AggCrimeTask(Task):
    priority = 50

    def __init__(self, primary_crime: str, primary_threshold: int,
                 away_crime: str, away_threshold: int,
                 armed_agg_private: bool = False, armed_agg_drug_house: bool = False,
                 armed_payback_private: bool = False, armed_payback_public: bool = False,
                 fallback_to_away: bool = False):
        self.primary_crime = primary_crime
        self.primary_threshold = primary_threshold
        self.away_crime = away_crime
        self.away_threshold = away_threshold
        self.armed_agg_private = armed_agg_private
        self.armed_agg_drug_house = armed_agg_drug_house
        self.armed_payback_private = armed_payback_private
        self.armed_payback_public = armed_payback_public
        self.fallback_to_away = fallback_to_away
        self._cooldown_until: float = 0.0
        self._hack_exhausted: bool = False

    def _pick_crime(self, state: GameState):
        if self.primary_crime == HACK_CRIME:
            if not state.in_home_city():
                # Out of home city — use away crime directly
                if self.away_crime and state.energy >= self.away_threshold:
                    return self.away_crime, self.away_threshold
                return None, 0
            # In home city
            if not self._hack_exhausted:
                if state.energy >= self.primary_threshold:
                    return self.primary_crime, self.primary_threshold
                return None, 0
            # Hack exhausted — try fallback if enabled
            if self.fallback_to_away and self.away_crime and state.energy >= self.away_threshold:
                return self.away_crime, self.away_threshold
            return None, 0
        if state.energy >= self.primary_threshold:
            return self.primary_crime, self.primary_threshold
        return None, 0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in:
            return False
        if time.monotonic() < self._cooldown_until:
            return False
        crime, _ = self._pick_crime(state)
        return crime is not None

    def run(self, state: GameState, executor):
        crime, threshold = self._pick_crime(state)
        if not crime:
            return

        if crime == "armed":
            executor.execute(Action("do_armed_robbery",
                threshold=threshold,
                agg_private=self.armed_agg_private,
                agg_drug_house=self.armed_agg_drug_house,
                payback_private=self.armed_payback_private,
                payback_public=self.armed_payback_public,
            ), state)
        else:
            executor.execute(Action("do_crime", crime=crime, threshold=threshold), state)

        if getattr(state, "_agg_targets_exhausted", False):
            state._agg_targets_exhausted = False

            if (self.primary_crime == HACK_CRIME and self.fallback_to_away
                    and self.away_crime and state.in_home_city()):
                if not self._hack_exhausted:
                    # Hack just exhausted — switch to fallback, no cooldown yet
                    self._hack_exhausted = True
                    state.add_log("Hack targets exhausted — falling back to away crime.")
                else:
                    # Fallback also exhausted — cooldown, reset for next cycle
                    self._hack_exhausted = False
                    self._cooldown_until = time.monotonic() + COOLDOWN_SECONDS
                    state.add_log("All targets exhausted — 3 minute cooldown started.")
            else:
                self._cooldown_until = time.monotonic() + COOLDOWN_SECONDS
                state.add_log("All targets exhausted — 3 minute cooldown started.")
        elif self._hack_exhausted:
            # Away crime ran and did not exhaust — go back to hack on next tick
            self._hack_exhausted = False
