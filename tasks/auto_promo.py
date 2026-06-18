"""
Checks main.asp when rank_progress = 100% and submits the configured A/B choice
if the game redirects to a promotion page.
"""

import time
import config as cfg
import browser
import urls
from state import GameState, parse_state
from tasks.base import Task
from promotions import PROMO_BY_RANK, get_choice, match_url

_CHECK_INTERVAL = 60  # seconds — don't hammer; check once per minute at most


class AutoPromoTask(Task):
    priority = 95
    label = "Auto Promo"

    def __init__(self):
        self._last_run: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.rank_progress < 100:
            return False
        if not cfg.load().get("promo", {}).get("auto_promo", {}).get("enabled", False):
            return False
        if state.snipe_top_job_pending:
            return False
        if state.next_rank not in PROMO_BY_RANK:
            return False
        return time.monotonic() - self._last_run >= _CHECK_INTERVAL

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()

        try:
            html = browser.navigate(urls.BASE_URL + "/main.asp")
            parse_state(html, browser.current_url(), state)
        except Exception as e:
            state.add_log(f"AutoPromo: nav error: {e}")
            return

        promo = match_url(browser.current_url())
        if not promo:
            return  # no promotion offered right now

        choice = get_choice(promo["slug"])
        option_label = promo["a"] if choice == "A" else promo["b"]

        try:
            page = browser.page()
            radios = page.query_selector_all("input[type='radio']")
            idx = 0 if choice == "A" else 1
            target = radios[idx] if len(radios) > idx else (radios[0] if radios else None)
            if target:
                target.click()
            page.click("input[type='submit']")
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            parse_state(page.content(), page.url, state)
            state.add_log(
                f"Auto-promo: {promo['rank']} — option {choice} ({option_label}) submitted."
            )
        except Exception as e:
            state.add_log(f"AutoPromo: submit error: {e}")
