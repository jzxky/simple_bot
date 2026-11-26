"""
Hammers main.asp until the promotion page for the target top job appears,
then submits it and makes the forum announcement (promo_post.py) if a thread
ID is configured; whatever isn't confirmed is retried by PromoForumPostTask.

Two modes (config: promo.snipe_own_tab, default on):
  - Own tab: runs in the side browser (side_browser.py) — a separate patchright
    instance on its own thread — so the refresh loop is never held up by the
    main bot loop. The scheduler only launches it; the main loop keeps running
    every other task on the main browser meanwhile.
  - Main tab: runs inline on the main browser tab. Every other task waits until
    the snipe ends (promotion, timeout, cancel or Stop).

Either way it starts a main.asp load every promo.snipe_interval seconds
(default 1, re-read every few seconds so a change applies mid-snipe), or
immediately after the previous load if that took longer.
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
SNIPE_INTERVAL = 1.0     # default seconds between the starts of consecutive main.asp loads
MIN_SNIPE_INTERVAL = 0.0  # 0 = back-to-back loads
_INTERVAL_RELOAD_EVERY = 5.0  # seconds between config re-reads of the interval
_NAV_ERROR_LOG_EVERY = 30  # log 1st, 31st, 61st... consecutive nav error


def snipe_interval(c: dict = None) -> float:
    """Seconds between the starts of consecutive main.asp loads (promo.snipe_interval)."""
    c = c if c is not None else cfg.load()
    try:
        v = float(c.get("promo", {}).get("snipe_interval", SNIPE_INTERVAL))
    except (TypeError, ValueError):
        return SNIPE_INTERVAL
    if v != v:  # NaN
        return SNIPE_INTERVAL
    return max(MIN_SNIPE_INTERVAL, v)


def own_tab_enabled(c: dict = None) -> bool:
    c = c if c is not None else cfg.load()
    return bool(c.get("promo", {}).get("snipe_own_tab", True))


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
        c = cfg.load()
        interval = snipe_interval(c)
        state.snipe_active = True
        if not own_tab_enabled(c):
            state.add_log(f"SnipeTopJob: starting in the main tab — targeting {top_job}, "
                          f"refreshing main.asp every {interval:g}s for up to 30 minutes. "
                          f"Other tasks wait until the snipe ends.")
            self._main_tab_snipe(state, promo_url, top_job)
            return
        state.add_log(f"SnipeTopJob: starting in its own tab — targeting {top_job}, "
                      f"refreshing main.asp every {interval:g}s for up to 30 minutes.")
        headless = c.get("misc", {}).get("headless", False)
        # Runs in its own side-browser lane, alongside any crime run. An armed
        # robbery run (which can hospitalise the character) sees snipe_active
        # and stops at its next attempt.
        self._job = side_browser.submit(
            "snipe", "snipe",
            lambda side, job: self._snipe_job(side, job, state, promo_url, top_job),
            cookies=browser.export_cookies(), headless=headless,
        )

    # ------------------------------------------------------------------
    # Main-tab mode
    # ------------------------------------------------------------------

    def _main_tab_snipe(self, state: GameState, promo_url: str, top_job: str):
        """Main thread: run the refresh loop on the main browser tab, blocking
        the bot loop until it ends. Stop and the Cancel Snipe button both set
        _cancel_snipe_event, which the loop checks between loads."""
        import bot as _bot
        promoted = False
        pg = None
        try:
            pg = browser.page()
            if not state.in_home_city():
                state.add_log(f"SnipeTopJob: not in home city ({state.home_city}), travelling from {state.current_city}.")
                self._inline_travel(pg, state.home_city, state)
            promoted = self._snipe_loop(
                pg, state, promo_url, top_job,
                stop_reason=lambda: None,
                wait=_bot._cancel_snipe_event.wait,
                on_session_lost=lambda: (state.add_log(
                    "SnipeTopJob: main tab logged out — stopping; the bot will log back in."), False)[1],
            )
        except Exception as e:
            if browser.is_lost_error(e):
                state.add_log(f"SnipeTopJob: main browser lost — {e}")
            else:
                state.add_log(f"SnipeTopJob: error: {e}")
        finally:
            self._finish(state, top_job, pg, promoted, side=None)

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

            promoted = self._snipe_loop(
                pg, state, promo_url, top_job,
                stop_reason=lambda: (job.cancel_reason or "cancelled") if job.cancel.is_set() else None,
                wait=job.cancel.wait,
                on_session_lost=lambda: self._side_session_lost(side, job, state),
            )
        finally:
            self._finish(state, top_job, pg, promoted, side=side)

    def _side_session_lost(self, side, job, state: GameState) -> bool:
        state.add_log("SnipeTopJob: side browser session lost — fetching fresh cookies.")
        if not side.refresh_cookies(job):
            state.add_log("SnipeTopJob: no fresh session available — stopping.")
            return False
        return True

    def _snipe_loop(self, pg, state: GameState, promo_url: str, top_job: str,
                    stop_reason, wait, on_session_lost) -> bool:
        """Refresh main.asp until promoted (True) or stopped / timed out (False).

        stop_reason() -> str | None: a reason to stop now (besides the Cancel
        Snipe button). wait(seconds): sleeps, waking early on a cancel.
        on_session_lost() -> bool: called on a logged-out page; True to carry on.
        """
        import bot as _bot
        deadline = time.monotonic() + SNIPE_TIMEOUT
        interval = snipe_interval()
        interval_read_at = time.monotonic()
        next_at = time.monotonic()
        nav_errors = 0
        cf_warned = False
        while True:
            if _bot._cancel_snipe_event.is_set():
                _bot._cancel_snipe_event.clear()
                state.add_log("SnipeTopJob: cancelled by user.")
                return False
            reason = stop_reason()
            if reason:
                state.add_log(f"SnipeTopJob: stopped — {reason}.")
                return False
            now = time.monotonic()
            if now >= deadline:
                state.add_log("SnipeTopJob: timed out after 30 minutes without promotion.")
                return False
            wait_s = next_at - now
            if wait_s > 0:
                # Short slices so a cancel is noticed promptly.
                wait(min(wait_s, 0.25))
                continue
            if now - interval_read_at >= _INTERVAL_RELOAD_EVERY:
                interval_read_at = now
                new_interval = snipe_interval()
                if new_interval != interval:
                    state.add_log(f"SnipeTopJob: refresh interval changed to {new_interval:g}s.")
                    interval = new_interval
            next_at = now + interval

            try:
                html = browser.navigate_page(pg, urls.BASE_URL + "/main.asp")
            except Exception as e:
                if browser.is_lost_error(e):
                    state.add_log(f"SnipeTopJob: browser lost — {e}")
                    return False
                if nav_errors % _NAV_ERROR_LOG_EVERY == 0:
                    state.add_log(f"SnipeTopJob: nav error: {e}")
                nav_errors += 1
                continue
            nav_errors = 0

            if "Just a moment" in (pg.title() or ""):
                if not cf_warned:
                    state.add_log("SnipeTopJob: Cloudflare challenge in the snipe tab — "
                                  "complete it in that window; still retrying.")
                    cf_warned = True
                continue
            cf_warned = False

            if pg.url.rstrip("/") == urls.BASE_URL + "/default.asp":
                if not on_session_lost():
                    return False
                continue

            temp = GameState()
            parse_state(html, pg.url, temp)

            if temp.server_time:
                state.server_time = temp.server_time
                state.server_time_monotonic = temp.server_time_monotonic

            if temp.occupation == top_job:
                state.occupation = temp.occupation
                state.add_log(f"SnipeTopJob: occupation updated to {top_job} via state parse.")
                return True

            if pg.url.rstrip("/") == promo_url.rstrip("/"):
                state.add_log("SnipeTopJob: promotion page detected — submitting.")
                if self._submit_promo(state, top_job, pg):
                    return True

    def _finish(self, state: GameState, top_job: str, pg, promoted: bool, side=None):
        """Shared clean-up for both modes. side is None in main-tab mode (the
        main tab is left open)."""
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
        if pg is not None and side is not None:
            side.close_page(pg)
        if promoted:
            # New rank → the available earns often change; the main bot
            # loop refreshes the list.
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
