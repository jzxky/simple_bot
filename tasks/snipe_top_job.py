"""
Hammers main.asp until the promotion page for the target top job appears,
then submits it and posts a forum announcement if a thread ID is configured
and the character is in their home city.
"""

import time
import config as cfg
import browser
import urls
from state import GameState, parse_state, SERVER_TIME_FMT
from tasks.base import Task
from tasks.check_top_job import _top_job_map

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
            and state.occupation in _top_job_map()
        )

    def run(self, state: GameState, executor):
        promo_url = state.snipe_top_job_promo_url
        top_job = _top_job_map().get(state.occupation, ("Unknown", ""))[0]
        state.add_log(f"SnipeTopJob: starting — targeting {top_job}, hammering main.asp for up to 30 minutes.")
        deadline = time.monotonic() + SNIPE_TIMEOUT
        promoted = False

        while time.monotonic() < deadline:
            try:
                html = browser.navigate(urls.BASE_URL + "/main.asp")
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

        if promoted:
            self._post_forum(state, top_job)

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

    def _post_forum(self, state: GameState, top_job: str):
        thread_id = cfg.load().get("promo", {}).get("top_job_thread_id", "").strip()
        if not thread_id:
            return

        if not state.in_home_city():
            state.add_log("SnipeTopJob: skipping forum post — not in home city.")
            return

        ts = state.server_time.strftime(SERVER_TIME_FMT) if state.server_time else "?"
        message = f"{state.own_name} - {top_job} - {ts}"
        post_url = urls.BASE_URL + f"/forum/postreply.asp?t={thread_id}"
        try:
            page = browser.page()
            page.goto(post_url, wait_until="domcontentloaded", timeout=15000)
            page.fill("textarea#body", message)
            page.click("input[name='Submit']")
            page.wait_for_load_state("domcontentloaded", timeout=10000)
            state.add_log(f"SnipeTopJob: forum post made — \"{message}\".")
        except Exception as e:
            state.add_log(f"SnipeTopJob: forum post error: {e}")
