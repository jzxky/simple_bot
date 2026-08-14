import queue

from tasks.base import Task, Action
from state import GameState
import player_db


class ScrapePlayersTask(Task):
    priority = 60
    label = "Scrape Players"

    def __init__(self, q: queue.Queue):
        self._queue = q

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not self._queue.empty()

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        try:
            item = self._queue.get_nowait()
        except Exception:
            return
        if isinstance(item, str):
            state.add_log(f"Scrape: starting for {item}")
            executor.execute(Action("scrape_player", username=item), state)
            state.add_log(f"Scrape: finished for {item}")
            return
        names = player_db.get_monitored_players()
        if not names:
            state.add_log("Scrape: no monitored players")
            return
        state.add_log(f"Scrape: starting for {len(names)} player(s)")
        for name in names:
            executor.execute(Action("scrape_player", username=name), state)
        state.add_log("Scrape: finished")
