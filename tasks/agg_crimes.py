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
                 away_crime: str, away_threshold: int):
        self.primary_crime = primary_crime
        self.primary_threshold = primary_threshold
        self.away_crime = away_crime
        self.away_threshold = away_threshold
        self._cooldown_until: float = 0.0

    def _pick_crime(self, state: GameState):
        if self.primary_crime == HACK_CRIME and not state.in_home_city():
            if self.away_crime and state.energy >= self.away_threshold:
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
        executor.execute(Action("do_crime", crime=crime, threshold=threshold), state)
        if getattr(state, "_agg_targets_exhausted", False):
            self._cooldown_until = time.monotonic() + COOLDOWN_SECONDS
            state._agg_targets_exhausted = False
            state.add_log("All targets exhausted — 3 minute cooldown started.")
