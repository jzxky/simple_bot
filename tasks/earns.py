"""
Checks the earn queue every 30 minutes and tops it up to 200 if below 10.
"""

from tasks.base import TimerTask, Action
from state import GameState

EARN_URL = "https://mafiamatrix.com/income/earn.asp"
QUEUE_MIN = 10
QUEUE_MAX = 200


class EarnsTask(TimerTask):
    def __init__(self, earn_type: str, interval_minutes: float = 30):
        super().__init__(priority=30, interval_seconds=interval_minutes * 60)
        self.earn_type = earn_type

    def _on_fire(self, state: GameState):
        if not state.logged_in:
            return None
        return Action("check_earns", earn_type=self.earn_type)
