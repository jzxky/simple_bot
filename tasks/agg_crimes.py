"""
Aggravated crime task. Selects the crime, optionally checks weapon,
then iterates through targets — all in a single run() call.
"""

from tasks.base import Task, Action
from state import GameState

WEAPON_CRIMES = {"mugging", "armed_robbery"}
HOME_CITY_CRIMES = {"hack"}


class AggCrimeTask(Task):
    priority = 50

    def __init__(self, primary_crime: str, primary_threshold: int,
                 secondary_crime: str, secondary_threshold: int):
        self.primary_crime = primary_crime
        self.primary_threshold = primary_threshold
        self.secondary_crime = secondary_crime
        self.secondary_threshold = secondary_threshold

    def _pick_crime(self, state: GameState):
        for crime, threshold in [
            (self.primary_crime, self.primary_threshold),
            (self.secondary_crime, self.secondary_threshold),
        ]:
            if crime in HOME_CITY_CRIMES and not state.in_home_city():
                continue
            if state.energy >= threshold:
                return crime, threshold
        return None, 0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in:
            return False
        crime, _ = self._pick_crime(state)
        return crime is not None

    def run(self, state: GameState, executor):
        crime, _ = self._pick_crime(state)
        if not crime:
            return
        executor.execute(Action("do_crime", crime=crime), state)
