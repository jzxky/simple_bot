"""
Aggravated crime task. Attempts primary crime, falls back to secondary.
Iterates through the player list until a success or exhaustion.
"""

from tasks.base import Task, Action
from state import GameState

CRIME_URL = "https://mafiamatrix.com/income/agcrime.asp"

WEAPON_CRIMES = {"mugging", "armed_robbery"}
HOME_CITY_CRIMES = {"hack"}

# Crimes that need a pistol or baseball bat specifically
MUGGING_WEAPONS = {"Baseball Bat", "Pistol"}
# Body parts are not valid weapons for armed robbery
BODY_PARTS = {"Arms", "Legs", "Eyes", "Brain", "Heart"}


class AggCrimeTask(Task):
    def __init__(self, primary_crime: str, primary_threshold: int,
                 secondary_crime: str, secondary_threshold: int):
        super().__init__(priority=50)
        self.primary_crime = primary_crime
        self.primary_threshold = primary_threshold
        self.secondary_crime = secondary_crime
        self.secondary_threshold = secondary_threshold
        self._selected_crime: str = ""
        self._phase = "select"  # select → iterate → done

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in:
            return False
        crime, threshold = self._pick_crime(state)
        if not crime:
            return False
        return state.energy >= threshold

    def _pick_crime(self, state: GameState):
        if self._crime_available(self.primary_crime, state):
            return self.primary_crime, self.primary_threshold
        if self._crime_available(self.secondary_crime, state):
            return self.secondary_crime, self.secondary_threshold
        return None, 0

    def _crime_available(self, crime: str, state: GameState) -> bool:
        if crime in HOME_CITY_CRIMES and not state.in_home_city():
            return False
        return True

    def run(self, state: GameState):
        crime, threshold = self._pick_crime(state)
        if not crime:
            return None
        self._selected_crime = crime

        if self._phase == "select":
            self._phase = "weapon_check" if crime in WEAPON_CRIMES else "iterate"
            return Action("select_crime", crime=crime)

        if self._phase == "weapon_check":
            self._phase = "iterate"
            return Action("check_weapon", crime=crime)

        if self._phase == "iterate":
            return Action("iterate_crime", crime=crime)

        return None

    def reset(self):
        """Call after a crime cycle completes (success or exhaustion)."""
        self._phase = "select"
        self._selected_crime = ""
        self.is_complete = False
