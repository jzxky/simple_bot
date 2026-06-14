"""
Checks the Chicago bionics store for wanted items and purchases them.

Runs only when current_city is Chicago and bionics.enabled in config,
at the configured interval. When use_time_window is enabled, the bot
parses the in-game time from div.serverTime on the current page and only
runs if that time falls within the configured window.

Auto-restock detection: if enabled and a restock is detected (all items
were 0, now at least one is > 1), predicts next restocks at +10.5h and
+13.5h and checks more frequently (every 1 minute) within 15 minutes of
each predicted window.
"""

import re
import time
from datetime import datetime
from tasks.base import Task, Action
from state import GameState

BIONIC_ITEMS = ["arms", "legs", "eyes", "brain", "heart"]

_RESTOCK_OFFSETS_H = (10.5, 13.5)
_RESTOCK_MARGIN_S  = 15 * 60
_RAPID_INTERVAL_S  = 60


def _parse_ingame_hhmm(page_content: str) -> "str | None":
    """Extract HH:MM from div.serverTime on the current page."""
    m = re.search(r'class="serverTime"[^>]*>([^<]+)<', page_content)
    if not m:
        return None
    # e.g. "6/14/2026 2:40:41 AM"
    parts = m.group(1).strip().split(" ", 1)
    if len(parts) < 2:
        return None
    try:
        return datetime.strptime(parts[1], "%I:%M:%S %p").strftime("%H:%M")
    except ValueError:
        return None


def _in_window(ingame_hhmm: "str | None", start_str: str, end_str: str) -> bool:
    if ingame_hhmm is None:
        return True
    return start_str <= ingame_hhmm <= end_str


class BionicsTask(Task):
    priority = 52
    label = "Bionics Store"

    def __init__(self):
        self._last_run: float = 0.0
        self._prev_stock: dict = {}
        self._predicted_restocks: list = []
        self.last_views: "tuple[int,int] | None" = None  # (current, max)

    def _near_predicted_restock(self) -> bool:
        now = time.time()
        return any(abs(now - t) <= _RESTOCK_MARGIN_S for t in self._predicted_restocks)

    def _interval(self, cfg_minutes: int) -> float:
        if self._near_predicted_restock():
            return _RAPID_INTERVAL_S
        return cfg_minutes * 60

    def can_run(self, state: GameState) -> bool:
        import config as cfg
        import browser
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.current_city.lower() != "chicago":
            return False
        b = cfg.load().get("bionics", {})
        if not b.get("enabled", False):
            return False
        if b.get("use_time_window", False) and not self._near_predicted_restock():
            ingame = _parse_ingame_hhmm(browser.page().content())
            if not _in_window(ingame, b.get("window_start", "00:00"), b.get("window_end", "23:59")):
                return False
        interval = self._interval(int(b.get("check_interval_minutes", 5)))
        return time.monotonic() - self._last_run >= interval

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()
        executor.execute(Action("check_bionics", _task=self), state)

    def record_stock(self, new_stock: dict, auto_restock_enabled: bool):
        if auto_restock_enabled and self._prev_stock:
            all_were_zero = all(self._prev_stock.get(i, 0) == 0 for i in BIONIC_ITEMS)
            any_now_positive = any(new_stock.get(i, 0) > 1 for i in BIONIC_ITEMS)
            if all_were_zero and any_now_positive:
                now = time.time()
                self._predicted_restocks = [
                    now + h * 3600 for h in _RESTOCK_OFFSETS_H
                ]
        self._prev_stock = dict(new_stock)
