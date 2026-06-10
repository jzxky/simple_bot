"""
Hammers main.asp until the Hospital Director promotion page appears,
submits it, then posts a forum announcement. Blocks the scheduler
for up to 30 minutes.
"""

import time
from datetime import datetime
from bs4 import BeautifulSoup
import browser
from state import GameState, parse_state
from tasks.base import Task

PLAY_URL      = "https://mafiamatrix.com/main.asp"
PROMO_URL     = "https://mafiamatrix.com/promotion/hospitaldirector.asp"
FORUM_POST_URL = "https://mafiamatrix.com/forum/postreply.asp?t=9995"
SNIPE_TIMEOUT = 30 * 60  # seconds
TARGET_OCC    = "Hospital Director"


class SnipeTopJobTask(Task):
    priority = 99
    label = 'Snipe Top Job'

    def can_run(self, state: GameState) -> bool:
        return (
            state.logged_in
            and not state.in_jail
            and state.snipe_top_job_pending
            and state.occupation != TARGET_OCC
        )

    def run(self, state: GameState, executor):
        state.add_log("SnipeTopJob: starting — hammering main.asp for up to 30 minutes.")
        deadline = time.monotonic() + SNIPE_TIMEOUT
        promoted = False

        while time.monotonic() < deadline:
            try:
                html = browser.navigate(PLAY_URL)
                parse_state(html, browser.current_url(), state)
            except Exception as e:
                state.add_log(f"SnipeTopJob: nav error: {e}")
                continue

            if state.occupation == TARGET_OCC:
                state.add_log("SnipeTopJob: occupation updated to Hospital Director via state parse.")
                promoted = True
                break

            if browser.current_url().rstrip("/") == PROMO_URL.rstrip("/"):
                state.add_log("SnipeTopJob: promotion page detected — submitting.")
                promoted = self._submit_promo(state)
                if promoted:
                    break

        if not promoted:
            state.add_log("SnipeTopJob: timed out after 30 minutes without promotion.")

        state.snipe_top_job_pending = False

        if promoted:
            self._post_forum(state)

    def _submit_promo(self, state: GameState) -> bool:
        try:
            page = browser.page()
            radio = page.query_selector("input[type='radio']")
            if radio:
                radio.click()
            page.click("input[type='submit']")
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            html = page.content()
            parse_state(html, page.url, state)
            if state.occupation == TARGET_OCC:
                state.add_log("SnipeTopJob: promotion successful!")
                return True
            state.add_log("SnipeTopJob: form submitted but occupation not updated yet.")
            return False
        except Exception as e:
            state.add_log(f"SnipeTopJob: promo submit error: {e}")
            return False

    def _post_forum(self, state: GameState):
        try:
            ts = state.server_time.strftime("%H:%M:%S") if state.server_time else datetime.utcnow().strftime("%H:%M:%S")
            message = f"Serotonin - Hospital Director - {ts}"
            page = browser.page()
            page.goto(FORUM_POST_URL, wait_until="domcontentloaded", timeout=15000)
            page.fill("textarea#body", message)
            page.click("input[name='Submit']")
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            state.add_log(f"SnipeTopJob: forum post made — \"{message}\".")
        except Exception as e:
            state.add_log(f"SnipeTopJob: forum post error: {e}")
