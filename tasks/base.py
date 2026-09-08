"""
Task base class and Action dataclass.
"""

from abc import ABC, abstractmethod


class Action:
    def __init__(self, kind: str, **params):
        self.kind = kind
        self.params = params

    def __repr__(self):
        return f"Action({self.kind!r}, {self.params})"


class Task(ABC):
    priority: int = 0
    label: str = ""  # display name shown in UI; defaults to class name if empty
    run_in_hospital: bool = False  # if False, task is paused while in_hospital
    # If True, this task may travel/change the bot's current city. Skipped while
    # the aggravated-crimes tab is active (state.agg_tab_active) — a mid-run city
    # change would invalidate the crime tab's target list and city context.
    changes_city: bool = False

    def can_run(self, state) -> bool:
        return True

    def blocked_reasons(self, state) -> list:
        return []

    @abstractmethod
    def run(self, state, executor):
        pass
