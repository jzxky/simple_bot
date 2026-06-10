"""
Periodically checks whether the player's eligible top job is vacant in their home city.
Sets snipe_top_job_pending to trigger SnipeTopJobTask when the position is open.
"""

import json
import time
import config as cfg
import browser
from state import GameState, parse_state
from tasks.base import Task

USERS_URL = "https://mafiamatrix.com/skin/updateusers.php?q=1"
PLAY_URL  = "https://mafiamatrix.com/main.asp"
_CHECK_INTERVAL = 5 * 60  # seconds

# Maps prerequisite occupation → (top job title, promo URL)
TOP_JOB_MAP = {
    "Fire Fighter":   ("Fire Chief",           "https://mafiamatrix.com/promotion/firechief.asp"),
    "Mortician":      ("Funeral Director",     "https://mafiamatrix.com/promotion/funeraldirector.asp"),
    "Undertaker":     ("Funeral Director",     "https://mafiamatrix.com/promotion/funeraldirector.asp"),
    "Loan Officer":   ("Bank Manager",         "https://mafiamatrix.com/promotion/bankmanager.asp"),
    "Surgeon":        ("Hospital Director",    "https://mafiamatrix.com/promotion/hospitaldirector.asp"),
    "Engineer":       ("Chief Engineer",       "https://mafiamatrix.com/promotion/chiefengineer.asp"),
    "Superintendent": ("Commissioner-General", "https://mafiamatrix.com/promotion/commissionergeneral.asp"),
}


class CheckTopJobTask(Task):
    priority = 40
    label = 'Check Top Job'

    def __init__(self):
        self._last_run: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in:
            return False
        if state.snipe_top_job_pending:
            return False
        if not cfg.load().get("promo", {}).get("monitor_top_job", False):
            return False
        if state.occupation not in TOP_JOB_MAP:
            return False
        if state.rank_progress < 100:
            return False
        return time.monotonic() - self._last_run >= _CHECK_INTERVAL

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()
        top_job, promo_url = TOP_JOB_MAP[state.occupation]

        try:
            browser.page().goto(USERS_URL, wait_until="domcontentloaded", timeout=15000)
            raw = json.loads(browser.page().inner_text("body"))
            browser.page().goto(PLAY_URL, wait_until="domcontentloaded", timeout=15000)
            parse_state(browser.page().content(), browser.current_url(), state)
        except Exception as e:
            state.add_log(f"CheckTopJob: fetch error: {e}")
            return

        match = next(
            (p["userName"] for p in raw
             if p.get("userHomeCity", "").strip() == state.home_city
             and p.get("userOccupation", "").strip() == top_job),
            None,
        )

        if match:
            state.add_log(f"CheckTopJob: {top_job} unavailable — occupied by: {match}")
        else:
            state.add_log(f"CheckTopJob: {top_job} is vacant — queuing snipe.")
            state.snipe_top_job_promo_url = promo_url
            state.snipe_top_job_pending = True
