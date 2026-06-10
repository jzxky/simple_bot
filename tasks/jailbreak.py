import queue
from tasks.base import Task, Action
from state import GameState


class PlanJailBreakTask(Task):
    priority = 80
    label = 'Plan Jail Break'

    def __init__(self, plan_queue: queue.Queue):
        self._queue = plan_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not state.in_jail and not self._queue.empty()

    def run(self, state: GameState, executor):
        try:
            params = self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("jailbreak_plan", **params), state)


class ExecuteJailBreakTask(Task):
    priority = 80
    label = 'Execute Jail Break'

    def __init__(self, execute_queue: queue.Queue):
        self._queue = execute_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and state.action_available() and not self._queue.empty()

    def run(self, state: GameState, executor):
        try:
            self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("jailbreak_execute"), state)


class CallOffJailBreakTask(Task):
    priority = 80
    label = 'Call Off Jail Break'

    def __init__(self, calloff_queue: queue.Queue):
        self._queue = calloff_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not self._queue.empty()

    def run(self, state: GameState, executor):
        try:
            self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("jailbreak_calloff"), state)
