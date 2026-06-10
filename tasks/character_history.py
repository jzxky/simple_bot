import queue
import time
import config as cfg
import character_history as ch
from tasks.base import Task
from state import GameState


class CharacterHistoryTask(Task):
    priority = 10
    label = 'Character History'

    def __init__(self, refresh_queue: queue.Queue):
        self._queue = refresh_queue
        self._last_run: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        c = cfg.load().get("character_history", {})
        if not c.get("enabled", False):
            return False
        # Manual refresh request
        if not self._queue.empty():
            return True
        interval = c.get("refresh_interval_minutes", 30) * 60
        return (time.time() - self._last_run) >= interval

    def run(self, state: GameState, executor):
        # Drain any pending manual request
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Exception:
                pass
        try:
            ch.fetch_and_save()
            self._last_run = time.time()
            state.add_log("Character history updated.")
        except Exception as e:
            state.add_log(f"Character history fetch failed: {e}")
