"""
Hammers main.asp until the promotion page for the target top job appears,
then submits it and posts a forum announcement if a thread ID is configured
and the character is in their home city.

Runs in a dedicated browser tab and thread so other tasks continue on the
main page.
"""

import re
import threading
import time
import config as cfg
import browser
import urls
from state import GameState, parse_state, state_lock, SERVER_TIME_FMT
from tasks.base import Task, Action
from tasks.check_top_job import TOP_JOB_MAP as _TOP_JOB_MAP
from promotions import PROMO_BY_RANK, get_choice

SNIPE_TIMEOUT = 30 * 60  # seconds


class SnipeTopJobTask(Task):
    priority = 99
    label = 'Snipe Top Job'

    def can_run(self, state: GameState) -> bool:
        t = state.snipe_top_job_thread
        if t and t.is_alive():
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
        t = state.snipe_top_job_thread
        if t and t.is_alive():
            reasons.append("Sniper thread already running")
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
        t = threading.Thread(
            target=self._snipe_loop,
            args=(state,),
            name="sniper",
            daemon=True,
        )
        state.snipe_top_job_thread = t
        t.start()

    def _snipe_loop(self, state: GameState):
        import bot as _bot
        snipe_page = None
        try:
            snipe_page = browser.new_page()
            with state_lock:
                promo_url = state.snipe_top_job_promo_url
                top_job = state.next_rank or "Unknown"
                home_city = state.home_city
                current_city = state.current_city

            state.add_log(f"SnipeTopJob: starting in new tab — targeting {top_job}, hammering main.asp for up to 30 minutes.")

            travel_failed = False
            if current_city and home_city and current_city != home_city:
                state.add_log(f"SnipeTopJob: not in home city ({home_city}), travelling from {current_city}.")
                travel_failed = not self._inline_travel(snipe_page, home_city, state)

            deadline = time.monotonic() + SNIPE_TIMEOUT
            promoted = False

            while time.monotonic() < deadline and not _bot._stop_event.is_set() and not _bot._cancel_snipe_event.is_set():
                try:
                    html = browser.navigate_page(snipe_page, urls.BASE_URL + "/main.asp")
                except Exception as e:
                    state.add_log(f"SnipeTopJob: nav error: {e}")
                    continue

                temp = GameState()
                parse_state(html, snipe_page.url, temp)

                with state_lock:
                    if temp.server_time:
                        state.server_time = temp.server_time
                        state.server_time_monotonic = temp.server_time_monotonic

                if temp.occupation == top_job:
                    with state_lock:
                        state.occupation = temp.occupation
                    state.add_log(f"SnipeTopJob: occupation updated to {top_job} via state parse.")
                    promoted = True
                    break

                if snipe_page.url.rstrip("/") == promo_url.rstrip("/"):
                    state.add_log("SnipeTopJob: promotion page detected — submitting.")
                    promoted = self._submit_promo(state, top_job, snipe_page)
                    if promoted:
                        break

            cancelled = _bot._cancel_snipe_event.is_set()
            _bot._cancel_snipe_event.clear()

            if not promoted:
                if cancelled:
                    state.add_log("SnipeTopJob: cancelled by user.")
                elif _bot._stop_event.is_set():
                    state.add_log("SnipeTopJob: stopped — bot shutting down.")
                else:
                    state.add_log("SnipeTopJob: timed out after 30 minutes without promotion.")

            with state_lock:
                state.snipe_top_job_pending = False
                state.snipe_top_job_promo_url = ""

            if promoted:
                if travel_failed:
                    state.add_log(f"SnipeTopJob: retrying travel to home city ({home_city}) after promotion.")
                    self._inline_travel(snipe_page, home_city, state)
                self._post_forum(state, top_job, snipe_page)

        except Exception as e:
            state.add_log(f"SnipeTopJob: fatal error in sniper thread: {e}")
            with state_lock:
                state.snipe_top_job_pending = False
                state.snipe_top_job_promo_url = ""
        finally:
            if snipe_page:
                browser.close_page(snipe_page)

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
                with state_lock:
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

        with state_lock:
            in_home = state.current_city != "" and state.current_city == state.home_city
        if not in_home:
            temp = GameState()
            html = browser.navigate_page(pg, urls.BASE_URL + "/main.asp")
            parse_state(html, pg.url, temp)
            in_home = temp.current_city != "" and temp.current_city == temp.home_city

        if not in_home:
            state.add_log("SnipeTopJob: skipping forum post — not in home city.")
            return

        with state_lock:
            ts = state.server_time.strftime(SERVER_TIME_FMT) if state.server_time else "?"
            own_name = state.own_name
        message = f"{own_name} - {top_job} - {ts}"
        post_url = urls.BASE_URL + f"/forum/postreply.asp?t={thread_id}"
        try:
            pg.goto(post_url, wait_until="domcontentloaded", timeout=15000)
            pg.fill("textarea#body", message)
            pg.click("input[name='Submit']")
            pg.wait_for_load_state("domcontentloaded", timeout=10000)
            state.add_log(f"SnipeTopJob: forum post made — \"{message}\".")
        except Exception as e:
            state.add_log(f"SnipeTopJob: forum post error: {e}")
