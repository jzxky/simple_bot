"""
Checks the Chicago bionics store for wanted items and purchases them.

Runs only when current_city is Chicago and bionics.enabled in config,
within the configured daily time window, and at the configured interval.

Auto-restock detection: if enabled and a restock is detected (all items
were 0, now at least one is > 1), predicts next restocks at +10.5h and
+13.5h and checks more frequently (every 1 minute) within 15 minutes of
each predicted window.
"""

import time
from datetime import datetime
from tasks.base import Task, Action
from state import GameState

BIONIC_ITEMS = ["arms", "legs", "eyes", "brain", "heart"]

_RESTOCK_OFFSETS_H = (10.5, 13.5)   # predicted restock times after detection
_RESTOCK_MARGIN_S  = 15 * 60        # check every minute within 15 min of prediction
_RAPID_INTERVAL_S  = 60


def _in_window(start_str: str, end_str: str) -> bool:
    """Return True if current local time is within [start, end] (HH:MM strings)."""
    try:
        now = datetime.now().strftime("%H:%M")
        return start_str <= now <= end_str
    except Exception:
        return True


class BionicsTask(Task):
    priority = 52
    label = "Bionics Store"

    def __init__(self):
        self._last_run: float = 0.0
        self._prev_stock: dict = {}           # item → last known stock
        self._predicted_restocks: list = []   # list of wall-clock times (time.time())

    def _near_predicted_restock(self) -> bool:
        now = time.time()
        return any(abs(now - t) <= _RESTOCK_MARGIN_S for t in self._predicted_restocks)

    def _interval(self, cfg_minutes: int) -> float:
        if self._near_predicted_restock():
            return _RAPID_INTERVAL_S
        return cfg_minutes * 60

    def can_run(self, state: GameState) -> bool:
        import config as cfg
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.current_city.lower() != "chicago":
            return False
        b = cfg.load().get("bionics", {})
        if not b.get("enabled", False):
            return False
        if not _in_window(b.get("window_start", "00:00"), b.get("window_end", "23:59")):
            if not self._near_predicted_restock():
                return False
        interval = self._interval(int(b.get("check_interval_minutes", 5)))
        return time.monotonic() - self._last_run >= interval

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()
        executor.execute(Action("check_bionics", _task=self), state)

    def record_stock(self, new_stock: dict, auto_restock_enabled: bool):
        """Called by handler after parsing the store. Detects restocks."""
        if auto_restock_enabled and self._prev_stock:
            all_were_zero = all(self._prev_stock.get(i, 0) == 0 for i in BIONIC_ITEMS)
            any_now_positive = any(new_stock.get(i, 0) > 1 for i in BIONIC_ITEMS)
            if all_were_zero and any_now_positive:
                now = time.time()
                self._predicted_restocks = [
                    now + h * 3600 for h in _RESTOCK_OFFSETS_H
                ]
        self._prev_stock = dict(new_stock)
