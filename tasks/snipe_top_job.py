"""
Hammers main.asp until the promotion page for the target top job appears,
then submits it and posts a forum announcement if a thread ID is configured
and the character is in their home city.

Runs in the side browser (side_browser.py) — a separate patchright instance on
its own thread — so the refresh loop is never held up by the main bot loop: it
starts a main.asp load every SNIPE_INTERVAL seconds (or immediately after the
previous load if that took longer). The scheduler only launches it; the main
loop keeps running every other task on the main browser meanwhile.
"""

import re
import time
import config as cfg
import browser
import side_browser
import urls
from state import GameState, parse_state, SERVER_TIME_FMT
from tasks.base import Task, Action
from tasks.check_top_job import TOP_JOB_MAP as _TOP_JOB_MAP
from promotions import PROMO_BY_RANK, get_choice

SNIPE_TIMEOUT = 30 * 60  # seconds
SNIPE_INTERVAL = 1.0     # seconds between the starts of consecutive main.asp loads
_NAV_ERROR_LOG_EVERY = 30  # log 1st, 31st, 61st... consecutive nav error


class SnipeTopJobTask(Task):
    priority = 99
    label = 'Snipe Top Job'

    def __init__(self):
        self._job = None

    def can_run(self, state: GameState) -> bool:
        if state.snipe_active:
            return False
        return (
            state.logged_in
            and not state.in_jail
            and state.snipe_top_job_pending
            and bool(state.snipe_top_job_promo_url)
            and state.next_rank in _TOP_JOB_MAP
        )

    def blocked_reasons(self, state):
        reasons = []
        if state.snipe_active:
            reasons.append("Snipe already active")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if not state.snipe_top_job_pending:
            reasons.append("No snipe pending")
        if not state.snipe_top_job_promo_url:
            reasons.append("No promo URL")
        if state.next_rank not in _TOP_JOB_MAP:
            reasons.append("Next rank not a top job")
        return reasons

    def run(self, state: GameState, executor):
        import bot as _bot
        promo_url = state.snipe_top_job_promo_url
        top_job = state.next_rank or "Unknown"
        _bot._cancel_snipe_event.clear()
        state.snipe_active = True
        state.add_log(f"SnipeTopJob: starting in side browser — targeting {top_job}, "
                      f"refreshing main.asp every {SNIPE_INTERVAL:g}s for up to 30 minutes.")
        headless = cfg.load().get("misc", {}).get("headless", False)
        # Runs in its own side-browser lane, alongside any crime run. An armed
        # robbery run (which can hospitalise the character) sees snipe_active
        # and stops at its next attempt.
        self._job = side_browser.submit(
            "snipe", "snipe",
            lambda side, job: self._snipe_job(side, job, state, promo_url, top_job),
            cookies=browser.export_cookies(), headless=headless,
        )

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    def _snipe_job(self, side, job, state: GameState, promo_url: str, top_job: str):
        import bot as _bot
        pg = None
        promoted = False
        try:
            try:
                pg = side.new_page(job)
            except Exception as e:
                state.add_log(f"SnipeTopJob: failed to open side browser: {e}")
                return

            if not state.in_home_city():
                state.add_log(f"SnipeTopJob: not in home city ({state.home_city}), travelling from {state.current_city}.")
                self._inline_travel(pg, state.home_city, state)

            deadline = time.monotonic() + SNIPE_TIMEOUT
            next_at = time.monotonic()
            nav_errors = 0
            cf_warned = False
            while True:
                if _bot._cancel_snipe_event.is_set():
                    _bot._cancel_snipe_event.clear()
                    state.add_log("SnipeTopJob: cancelled by user.")
                    return
                if job.cancel.is_set():
                    state.add_log(f"SnipeTopJob: stopped — {job.cancel_reason or 'cancelled'}.")
                    return
                if time.monotonic() >= deadline:
                    state.add_log("SnipeTopJob: timed out after 30 minutes without promotion.")
                    return
                wait = next_at - time.monotonic()
                if wait > 0:
                    # Short slices so a cancel is noticed promptly.
                    job.cancel.wait(min(wait, 0.25))
                    continue
                next_at = time.monotonic() + SNIPE_INTERVAL

                try:
                    html = browser.navigate_page(pg, urls.BASE_URL + "/main.asp")
                except Exception as e:
                    if browser.is_lost_error(e):
                        state.add_log(f"SnipeTopJob: side browser lost — {e}")
                        return
                    if nav_errors % _NAV_ERROR_LOG_EVERY == 0:
                        state.add_log(f"SnipeTopJob: nav error: {e}")
                    nav_errors += 1
                    continue
                nav_errors = 0

                if "Just a moment" in (pg.title() or ""):
                    if not cf_warned:
                        state.add_log("SnipeTopJob: Cloudflare challenge in the side browser — "
                                      "complete it in that window; still retrying.")
                        cf_warned = True
                    continue
                cf_warned = False

                if pg.url.rstrip("/") == urls.BASE_URL + "/default.asp":
                    state.add_log("SnipeTopJob: side browser session lost — fetching fresh cookies.")
                    if not side.refresh_cookies(job):
                        state.add_log("SnipeTopJob: no fresh session available — stopping.")
                        return
                    continue

                temp = GameState()
                parse_state(html, pg.url, temp)

                if temp.server_time:
                    state.server_time = temp.server_time
                    state.server_time_monotonic = temp.server_time_monotonic

                if temp.occupation == top_job:
                    state.occupation = temp.occupation
                    state.add_log(f"SnipeTopJob: occupation updated to {top_job} via state parse.")
                    promoted = True
                    return

                if pg.url.rstrip("/") == promo_url.rstrip("/"):
                    state.add_log("SnipeTopJob: promotion page detected — submitting.")
                    if self._submit_promo(state, top_job, pg):
                        promoted = True
                        return
        finally:
            try:
                if promoted and pg is not None:
                    if not state.in_home_city():
                        state.add_log(f"SnipeTopJob: retrying travel to home city ({state.home_city}) after promotion.")
                        self._inline_travel(pg, state.home_city, state)
                    self._post_forum(state, top_job, pg)
            except Exception as e:
                state.add_log(f"SnipeTopJob: post-promotion error: {e}")
            if pg is not None:
                side.close_page(pg)
            state.snipe_top_job_pending = False
            state.snipe_top_job_promo_url = ""
            state.snipe_active = False

    def stop(self, reason: str = "stopped"):
        """Main thread: ask a running snipe to stop."""
        if self._job is not None and not self._job.done.is_set():
            self._job.request_cancel(reason)

    def _inline_travel(self, pg, target_city: str, state: GameState) -> bool:
        from bs4 import BeautifulSoup
        try:
            html = browser.navigate_page(pg, urls.BASE_URL + "/travel/travel.asp")
            soup = BeautifulSoup(html, "html.parser")
            dest_map = {}
            for div in soup.find_all("div", class_="city-container"):
                inner = div.find("div", class_="city-travel-container")
                if not inner:
                    continue
                city_name = inner.get("id", "")
                link = inner.find("a", href=re.compile(r"depart\.asp\?destination="))
                if city_name and link:
                    dest_map[city_name.lower()] = link["href"]
            href = dest_map.get(target_city.lower())
            if not href:
                state.add_log(f"SnipeTopJob: {target_city} not available on travel.asp.")
                return False
            depart_url = href if href.startswith("http") else urls.BASE_URL + "/travel/" + href
            browser.navigate_page(pg, depart_url)
            state.add_log(f"SnipeTopJob: departed to {target_city} by vehicle.")
            return True
        except Exception as e:
            state.add_log(f"SnipeTopJob: inline travel error: {e}")
            return False

    def _submit_promo(self, state: GameState, top_job: str, pg) -> bool:
        try:
            promo_data = PROMO_BY_RANK.get(top_job, {})
            slug = promo_data.get("slug", "")
            choice = get_choice(slug) if slug else "A"
            radios = pg.query_selector_all("input[type='radio']")
            idx = 0 if choice == "A" else 1
            target = radios[idx] if len(radios) > idx else (radios[0] if radios else None)
            if target:
                target.click()
            pg.click("input[type='submit']")
            pg.wait_for_load_state("domcontentloaded", timeout=10000)
            temp = GameState()
            parse_state(pg.content(), pg.url, temp)
            if temp.occupation == top_job:
                state.occupation = temp.occupation
                msg = f"SnipeTopJob: promoted to {top_job} (option {choice})!"
                state.add_log(msg)
                if cfg.load().get("notifications", {}).get("promotion_success", False):
                    state.push_notification("promotion_success", msg)
                return True
            state.add_log("SnipeTopJob: form submitted but occupation not updated yet.")
            return False
        except Exception as e:
            state.add_log(f"SnipeTopJob: promo submit error: {e}")
            return False

    def _post_forum(self, state: GameState, top_job: str, pg):
        thread_id = cfg.load().get("promo", {}).get("top_job_thread_id", "").strip()
        if not thread_id:
            return

        if not state.in_home_city():
            temp = GameState()
            html = browser.navigate_page(pg, urls.BASE_URL + "/main.asp")
            parse_state(html, pg.url, temp)
            if not (temp.current_city and temp.current_city == temp.home_city):
                state.add_log("SnipeTopJob: skipping forum post — not in home city.")
                return

        ts = state.server_time.strftime(SERVER_TIME_FMT) if state.server_time else "?"
        message = f"{state.own_name} - {top_job} - {ts}"
        post_url = urls.BASE_URL + f"/forum/postreply.asp?t={thread_id}"
        try:
            pg.goto(post_url, wait_until="domcontentloaded", timeout=15000)
            pg.fill("textarea#body", message)
            pg.click("input[name='Submit']")
            pg.wait_for_load_state("domcontentloaded", timeout=10000)
            state.add_log(f"SnipeTopJob: forum post made — \"{message}\".")
        except Exception as e:
            state.add_log(f"SnipeTopJob: forum post error: {e}")
