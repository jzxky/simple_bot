"""
Casino task — plays the configured Beirut casino activity (Slots or Blackjack).
Optionally auto-travels to Beirut first if not already there.
"""

from tasks.base import Task, Action
from state import GameState


class CasinoTask(Task):
    priority = 50
    label = "Casino"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        import config as cfg
        return cfg.load().get("casino", {}).get("enabled", False)

    def run(self, state: GameState, executor):
        executor.execute(Action("play_casino"), state)
