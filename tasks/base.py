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

    def can_run(self, state) -> bool:
        return True

    @abstractmethod
    def run(self, state, executor):
        pass
