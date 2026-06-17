"""
Case work tasks for legit careers.
Each career sub-class declares eligible occupations and city restrictions.
"""

import time
from abc import abstractmethod
from tasks.base import Task, Action
from state import GameState


class CaseWorkTask(Task):
    priority = 50
    label = 'Case Work'

    ELIGIBLE_OCCUPATIONS: set = set()
    HOME_CITY_ONLY: bool = True

    def __init__(self, poll_interval: int = 31):
        self._poll_interval = poll_interval
        self._last_checked: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        if state.occupation not in self.ELIGIBLE_OCCUPATIONS:
            return False
        if self.HOME_CITY_ONLY and not state.in_home_city():
            return False
        if not state.timers.get("case", {}).get("ready", True):
            return False
        return time.monotonic() - self._last_checked >= self._poll_interval

    def run(self, state: GameState, executor):
        self._last_checked = time.monotonic()
        executor.execute(self._action(), state)

    @abstractmethod
    def _action(self) -> Action:
        pass


class EngineeringCaseWorkTask(CaseWorkTask):
    ELIGIBLE_OCCUPATIONS = {"Mechanic", "Technician", "Engineer", "Chief Engineer"}
    HOME_CITY_ONLY = False

    def __init__(self, poll_interval: int = 31, tasks: list = None):
        super().__init__(poll_interval)
        self._tasks = tasks or []

    def _action(self) -> Action:
        return Action("check_engineering_cases", tasks=self._tasks)


class HospitalCaseWorkTask(CaseWorkTask):
    ELIGIBLE_OCCUPATIONS = {"Nurse", "Doctor", "Surgeon", "Hospital Director"}
    HOME_CITY_ONLY = False  # DNA is filtered in the executor when away from home city

    def __init__(self, poll_interval: int = 31, tasks: list = None):
        super().__init__(poll_interval)
        self._tasks = tasks or []

    def _action(self) -> Action:
        return Action("check_hospital_cases", tasks=self._tasks)
