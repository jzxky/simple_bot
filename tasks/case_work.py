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
    USES_CASE_TIMER: bool = True  # banking laundering is poll-driven, not case-timer gated

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
        if self.USES_CASE_TIMER and not state.timer_ready("case"):
            return False
        return time.monotonic() - self._last_checked >= self._poll_interval

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.occupation not in self.ELIGIBLE_OCCUPATIONS:
            reasons.append("Wrong occupation")
        if self.HOME_CITY_ONLY and not state.in_home_city():
            reasons.append("Not in home city")
        if self.USES_CASE_TIMER and not state.timer_ready("case"):
            reasons.append("Case timer not ready")
        remaining = self._poll_interval - (time.monotonic() - self._last_checked)
        if remaining > 0:
            reasons.append(f"Poll interval ({int(remaining)}s)")
        return reasons

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


class FireCaseWorkTask(CaseWorkTask):
    ELIGIBLE_OCCUPATIONS = {"Volunteer Fire Fighter", "Fire Fighter", "Fire Chief"}
    HOME_CITY_ONLY = False

    def __init__(self, poll_interval: int = 31, tasks: list = None):
        super().__init__(poll_interval)
        self._tasks = tasks or []

    def _action(self) -> Action:
        return Action("check_fire_cases", tasks=self._tasks)


class LawyerCaseWorkTask(CaseWorkTask):
    ELIGIBLE_OCCUPATIONS = {"Lawyer"}
    HOME_CITY_ONLY = False
    USES_CASE_TIMER = True
    changes_city = True  # auto-travel path (config-gated); paused with the rest of the task while a crime tab is active

    def __init__(self, poll_interval: int = 31):
        super().__init__(poll_interval)

    def _action(self) -> Action:
        return Action("check_lawyer_cases")


class BankingCaseWorkTask(CaseWorkTask):
    ELIGIBLE_OCCUPATIONS = {"Bank Teller", "Loan Officer", "Bank Manager"}
    HOME_CITY_ONLY = True
    USES_CASE_TIMER = True  # gated by the case timer like the other case work tasks

    def __init__(self, poll_interval: int = 60):
        super().__init__(poll_interval)

    def _action(self) -> Action:
        return Action("check_banking_cases")
