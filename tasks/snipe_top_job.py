"""
Posts the target top job's promotion form (/promotion/<job>.asp) over and over
until the game accepts it, then makes the forum announcement (promo_post.py)
if a thread ID is configured; whatever isn't confirmed is retried by
PromoForumPostTask.

The promotion form is plain HTML with no token (option=one|two, B1=Continue,
action=choice), so it's sent straight from the side browser's request context
(sharing its login cookies) instead of loading main.asp, waiting for the
redirect to the promotion page and clicking through it. While the job is
taken, the game answers the POST with a redirect to main.asp, whose status bar
shows the occupation; once it's free, the POST itself promotes the character.

Runs in the side browser (side_browser.py) — a separate patchright instance on
its own thread — so the loop is never held up by the main bot loop: it sends a
POST every SNIPE_INTERVAL seconds (or immediately after the previous one if
that took longer). The scheduler only launches it; the main loop keeps running
every other task on the main browser meanwhile.
"""

import re
import time
import config as cfg
import browser
import side_browser
import urls
from state import GameState, parse_state
from tasks.base import Task, Action
from tasks.check_top_job import TOP_JOB_MAP as _TOP_JOB_MAP
from promotions import PROMO_BY_RANK, get_choice
import promo_post

SNIPE_TIMEOUT = 30 * 60  # seconds
SNIPE_INTERVAL = 1.0     # seconds between the starts of consecutive promotion POSTs
VERIFY_EVERY = 15.0      # also load main.asp this often, in case a POST's reply hides the occupation
POST_TIMEOUT = 15000     # ms
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
                      f"posting its promotion form every {SNIPE_INTERVAL:g}s for up to 30 minutes.")
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

            choice = self._choice(top_job)
            form = {"option": "one" if choice == "A" else "two", "B1": "Continue", "action": "choice"}
            main_url = urls.BASE_URL + "/main.asp"

            deadline = time.monotonic() + SNIPE_TIMEOUT
            next_at = time.monotonic()
            verify_at = time.monotonic() + VERIFY_EVERY
            nav_errors = 0
            cf_warned = False
            posts = 0
            while True:
                if _bot._cancel_snipe_event.is_set():
                    _bot._cancel_snipe_event.clear()
                    state.add_log("SnipeTopJob: cancelled by user.")
                    return
                if job.cancel.is_set():
                    state.add_log(f"SnipeTopJob: stopped — {job.cancel_reason or 'cancelled'}.")
                    return
                if time.monotonic() >= deadline:
                    state.add_log(f"SnipeTopJob: timed out after 30 minutes without promotion "
                                  f"({posts} promotion posts sent).")
                    return
                wait = next_at - time.monotonic()
                if wait > 0:
                    # Short slices so a cancel is noticed promptly.
                    job.cancel.wait(min(wait, 0.25))
                    continue
                next_at = time.monotonic() + SNIPE_INTERVAL

                # Every VERIFY_EVERY seconds a plain main.asp load instead of a
                # POST: confirms the occupation even if a POST's reply doesn't
                # carry the status bar, and keeps the session looking normal.
                verify = time.monotonic() >= verify_at
                try:
                    if verify:
                        verify_at = time.monotonic() + VERIFY_EVERY
                        html = browser.navigate_page(pg, main_url)
                        final_url = pg.url
                    else:
                        resp = pg.request.post(promo_url, form=form, timeout=POST_TIMEOUT)
                        html = resp.text()
                        final_url = resp.url
                        posts += 1
                except Exception as e:
                    if browser.is_lost_error(e):
                        state.add_log(f"SnipeTopJob: side browser lost — {e}")
                        return
                    if nav_errors % _NAV_ERROR_LOG_EVERY == 0:
                        state.add_log(f"SnipeTopJob: {'nav' if verify else 'post'} error: {e}")
                    nav_errors += 1
                    continue
                nav_errors = 0

                if "<title>Just a moment" in html[:5000]:
                    if not cf_warned:
                        state.add_log("SnipeTopJob: Cloudflare challenge in the side browser — "
                                      "complete it in that window; still retrying.")
                        cf_warned = True
                    # Load it in the window so it can be completed there.
                    if not verify:
                        verify_at = 0.0
                    continue
                cf_warned = False

                if final_url.rstrip("/").lower().endswith("/default.asp"):
                    state.add_log("SnipeTopJob: side browser session lost — fetching fresh cookies.")
                    if not side.refresh_cookies(job):
                        state.add_log("SnipeTopJob: no fresh session available — stopping.")
                        return
                    continue

                temp = GameState()
                parse_state(html, final_url, temp)

                if temp.server_time:
                    state.server_time = temp.server_time
                    state.server_time_monotonic = temp.server_time_monotonic

                if temp.occupation == top_job:
                    self._promoted(state, top_job, choice, temp.occupation)
                    promoted = True
                    return

                if verify:
                    if final_url.rstrip("/").lower() == promo_url.rstrip("/").lower():
                        # The game sent the plain page load to the promotion
                        # form: the POSTs aren't taking, so click through it.
                        state.add_log("SnipeTopJob: promotion page detected — submitting.")
                        if self._submit_promo(state, top_job, pg):
                            promoted = True
                            return
                    continue

                # The POST didn't land back on main.asp (whose status bar was
                # just parsed): something new happened, so check main.asp now.
                if not final_url.rstrip("/").lower().endswith("/main.asp"):
                    verify_at = 0.0
        finally:
            if promoted:
                # Recorded before anything else can fail: the main loop's
                # PromoForumPostTask retries the post until it's confirmed.
                try:
                    promo_post.mark_pending(state, top_job)
                except Exception as e:
                    state.add_log(f"SnipeTopJob: couldn't record the pending forum post: {e}")
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
            if promoted:
                # New rank → the available earns often change; the main bot
                # loop refreshes the list (this thread can't use the main browser).
                state.earn_catalog_refresh_pending = True
            state.snipe_top_job_pending = False
            state.snipe_top_job_promo_url = ""
            state.snipe_active = False

    def stop(self, reason: str = "stopped"):
        """Main thread: ask a running snipe to stop."""
        if self._job is not None and not self._job.done.is_set():
            self._job.request_cancel(reason)

    def _inline_travel(self, pg, target_city: str, state: GameState) -> bool:
        import travel_parser
        try:
            html = browser.navigate_page(pg, urls.BASE_URL + "/travel/travel.asp")
            dest = travel_parser.find_destination(
                travel_parser.parse_vehicle_destinations(html), target_city)
            if not dest:
                state.add_log(f"SnipeTopJob: {target_city} not available on travel.asp.")
                return False
            if not dest["open"]:
                is_home = target_city.lower() == (state.home_city or "").lower()
                if not dest["href"] or not (is_home or cfg.load().get("travel", {}).get("ignore_closed", False)):
                    state.add_log(f"SnipeTopJob: {target_city} is closed ({dest['reason']}).")
                    return False
                state.add_log(f"SnipeTopJob: {target_city} is closed ({dest['reason']}) — override on, travelling anyway.")
            href = dest["href"]
            depart_url = href if href.startswith("http") else urls.BASE_URL + "/travel/" + href
            browser.navigate_page(pg, depart_url)
            state.add_log(f"SnipeTopJob: departed to {target_city} by vehicle.")
            return True
        except Exception as e:
            state.add_log(f"SnipeTopJob: inline travel error: {e}")
            return False

    @staticmethod
    def _choice(top_job: str) -> str:
        slug = PROMO_BY_RANK.get(top_job, {}).get("slug", "")
        return get_choice(slug) if slug else "A"

    @staticmethod
    def _promoted(state: GameState, top_job: str, choice: str, occupation: str):
        state.occupation = occupation
        msg = f"SnipeTopJob: promoted to {top_job} (option {choice})!"
        state.add_log(msg)
        if cfg.load().get("notifications", {}).get("promotion_success", False):
            state.push_notification("promotion_success", msg)

    def _submit_promo(self, state: GameState, top_job: str, pg) -> bool:
        """Fallback: click through the promotion page the side browser is on."""
        try:
            choice = self._choice(top_job)
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
                self._promoted(state, top_job, choice, temp.occupation)
                return True
            state.add_log("SnipeTopJob: form submitted but occupation not updated yet.")
            return False
        except Exception as e:
            state.add_log(f"SnipeTopJob: promo submit error: {e}")
            return False

    def _post_forum(self, state: GameState, top_job: str, pg):
        """First attempt at the pending forum post, straight after the
        promotion, from the side browser. Anything left over is retried by
        PromoForumPostTask on the main tab."""
        if not promo_post.pending_for(state):
            return
        if not state.in_home_city():
            temp = GameState()
            html = browser.navigate_page(pg, urls.BASE_URL + "/main.asp")
            parse_state(html, pg.url, temp)
            if not (temp.current_city and temp.current_city == temp.home_city):
                state.add_log("SnipeTopJob: not in home city yet — the forum post will be made once home.")
                return
        try:
            promo_post.post_and_verify(pg, state)
        except Exception as e:
            state.add_log(f"SnipeTopJob: forum post error: {e} — will retry.")
