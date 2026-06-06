"""
Task base classes: Task, TimerTask, IterativeTask, EventDrivenTask.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Optional


class Action:
    def __init__(self, kind: str, **params):
        self.kind = kind
        self.params = params

    def __repr__(self):
        return f"Action({self.kind!r}, {self.params})"


class Task(ABC):
    def __init__(self, priority: int):
        self.priority = priority
        self.is_complete = False
        self._interrupted = False

    def interrupt(self):
        self._interrupted = True

    def resume(self):
        self._interrupted = False

    @abstractmethod
    def run(self, state) -> Optional[Action]:
        pass

    def can_run(self, state) -> bool:
        return not self.is_complete


class TimerTask(Task):
    """Fires at a fixed interval."""

    def __init__(self, priority: int, interval_seconds: float):
        super().__init__(priority)
        self.interval = interval_seconds
        self._last_fired: float = 0.0

    def can_run(self, state) -> bool:
        if self.is_complete:
            return False
        return time.monotonic() - self._last_fired >= self.interval

    def run(self, state) -> Optional[Action]:
        self._last_fired = time.monotonic()
        return self._on_fire(state)

    @abstractmethod
    def _on_fire(self, state) -> Optional[Action]:
        pass


class IterativeTask(Task):
    """Iterates over a list one item per tick, resumable after interruption."""

    def __init__(self, priority: int, items: list):
        super().__init__(priority)
        self._items = items
        self._index = 0

    def run(self, state) -> Optional[Action]:
        if self._index >= len(self._items):
            self.is_complete = True
            return None
        item = self._items[self._index]
        action = self._process_item(item, state)
        self._index += 1
        if self._index >= len(self._items):
            self.is_complete = True
        return action

    @abstractmethod
    def _process_item(self, item: Any, state) -> Optional[Action]:
        pass

    @property
    def progress(self) -> tuple:
        return self._index, len(self._items)


class EventDrivenTask(Task):
    """Triggers when a condition in state becomes true."""

    def __init__(self, priority: int):
        super().__init__(priority)

    @abstractmethod
    def condition(self, state) -> bool:
        pass

    def can_run(self, state) -> bool:
        return not self.is_complete and self.condition(state)
