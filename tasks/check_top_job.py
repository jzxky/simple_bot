"""
Periodically checks whether the player's eligible top job is vacant in their home city.
Sets snipe_top_job_pending to trigger SnipeTopJobTask when the position is open.
"""

import json
import time
import config as cfg
import browser
import urls
from state import GameState, parse_state
from tasks.base import Task

_CHECK_INTERVAL = 5 * 60  # seconds

# Maps prerequisite occupation → (top job title, promo path)
_TOP_JOB_PATHS = {
    "Fire Fighter":   ("Fire Chief",           "/promotion/firechief.asp"),
    "Mortician":      ("Funeral Director",     "/promotion/funeraldirector.asp"),
    "Undertaker":     ("Funeral Director",     "/promotion/funeraldirector.asp"),
    "Loan Officer":   ("Bank Manager",         "/promotion/bankmanager.asp"),
    "Surgeon":        ("Hospital Director",    "/promotion/hospitaldirector.asp"),
    "Engineer":       ("Chief Engineer",       "/promotion/chiefengineer.asp"),
    "Superintendent": ("Commissioner-General", "/promotion/commissionergeneral.asp"),
}


def _top_job_map() -> dict:
    return {occ: (title, urls.BASE_URL + path) for occ, (title, path) in _TOP_JOB_PATHS.items()}


TOP_JOB_MAP = _top_job_map()


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
        if state.occupation not in _TOP_JOB_PATHS:
            return False
        top_job = _TOP_JOB_PATHS[state.occupation][0]
        if state.next_rank != top_job:
            return False
        if state.rank_progress < 100:
            return False
        return time.monotonic() - self._last_run >= _CHECK_INTERVAL

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()
        top_job, promo_url = _top_job_map()[state.occupation]

        try:
            browser.page().goto(urls.BASE_URL + "/skin/updateusers.php?q=1", wait_until="domcontentloaded", timeout=15000)
            raw = json.loads(browser.page().inner_text("body"))
            browser.page().goto(urls.BASE_URL + "/main.asp", wait_until="domcontentloaded", timeout=15000)
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
