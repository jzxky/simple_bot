"""
Hammers main.asp until the promotion page for the target top job appears,
then submits it. Blocks the scheduler for up to 30 minutes.
"""

import time
from bs4 import BeautifulSoup
import browser
from state import GameState, parse_state
from tasks.base import Task
from tasks.check_top_job import TOP_JOB_MAP

PLAY_URL      = "https://mafiamatrix.com/main.asp"
SNIPE_TIMEOUT = 30 * 60  # seconds


class SnipeTopJobTask(Task):
    priority = 99
    label = 'Snipe Top Job'

    def can_run(self, state: GameState) -> bool:
        return (
            state.logged_in
            and not state.in_jail
            and state.snipe_top_job_pending
            and bool(state.snipe_top_job_promo_url)
            and state.occupation in TOP_JOB_MAP
        )

    def run(self, state: GameState, executor):
        promo_url = state.snipe_top_job_promo_url
        top_job = TOP_JOB_MAP.get(state.occupation, ("Unknown", ""))[0]
        state.add_log(f"SnipeTopJob: starting — targeting {top_job}, hammering main.asp for up to 30 minutes.")
        deadline = time.monotonic() + SNIPE_TIMEOUT
        promoted = False

        while time.monotonic() < deadline:
            try:
                html = browser.navigate(PLAY_URL)
                parse_state(html, browser.current_url(), state)
            except Exception as e:
                state.add_log(f"SnipeTopJob: nav error: {e}")
                continue

            if state.occupation == top_job:
                state.add_log(f"SnipeTopJob: occupation updated to {top_job} via state parse.")
                promoted = True
                break

            if browser.current_url().rstrip("/") == promo_url.rstrip("/"):
                state.add_log(f"SnipeTopJob: promotion page detected — submitting.")
                promoted = self._submit_promo(state, top_job)
                if promoted:
                    break

        if not promoted:
            state.add_log(f"SnipeTopJob: timed out after 30 minutes without promotion.")

        state.snipe_top_job_pending = False
        state.snipe_top_job_promo_url = ""

    def _submit_promo(self, state: GameState, top_job: str) -> bool:
        try:
            page = browser.page()
            radio = page.query_selector("input[type='radio']")
            if radio:
                radio.click()
            page.click("input[type='submit']")
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            parse_state(page.content(), page.url, state)
            if state.occupation == top_job:
                state.add_log(f"SnipeTopJob: promotion to {top_job} successful!")
                return True
            state.add_log("SnipeTopJob: form submitted but occupation not updated yet.")
            return False
        except Exception as e:
            state.add_log(f"SnipeTopJob: promo submit error: {e}")
            return False
