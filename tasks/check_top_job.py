"""
Periodically checks whether the Hospital Director position in Chicago is vacant.
If vacant, sets state.snipe_top_job_pending to trigger SnipeTopJobTask.
"""

import json
import time
import config as cfg
import browser
from state import GameState, parse_state
from tasks.base import Task

USERS_URL = "https://mafiamatrix.com/skin/updateusers.php?q=1"
PLAY_URL   = "https://mafiamatrix.com/main.asp"
_CHECK_INTERVAL = 5 * 60  # seconds


class CheckTopJobTask(Task):
    priority = 40
    label = 'Check Top Job'

    def __init__(self):
        self._last_run: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in:
            return False
        if state.occupation == "Hospital Director":
            return False
        if state.snipe_top_job_pending:
            return False
        promo_cfg = cfg.load().get("promo", {})
        if not promo_cfg.get("monitor_top_job", False):
            return False
        return time.monotonic() - self._last_run >= _CHECK_INTERVAL

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()
        try:
            browser.page().goto(USERS_URL, wait_until="domcontentloaded", timeout=15000)
            raw = json.loads(browser.page().inner_text("body"))
            browser.page().goto(PLAY_URL, wait_until="domcontentloaded", timeout=15000)
            html = browser.page().content()
            parse_state(html, browser.current_url(), state)
        except Exception as e:
            state.add_log(f"CheckTopJob: fetch error: {e}")
            return

        hd_taken = any(
            p.get("userHomeCity", "").strip() == "Chicago"
            and p.get("userOccupation", "").strip() == "Hospital Director"
            for p in raw
        )

        if hd_taken:
            state.add_log("CheckTopJob: Hospital Director in Chicago is occupied.")
        else:
            state.add_log("CheckTopJob: Hospital Director position is vacant — queuing snipe.")
            state.snipe_top_job_pending = True
