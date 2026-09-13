"""
Navigates to main.asp (or jail.asp for jail ranks) when rank_progress = 100%
to trigger a promotion redirect. The actual promo page submission is handled
by PromoPageTask, which detects promotion URLs.

Runs when auto-promo is enabled (regular ranks; top jobs are left to the
sniper).
"""

import time
import config as cfg
import browser
import urls
from state import GameState, parse_state
from tasks.base import Task
from promotions import PROMO_BY_RANK
from tasks.check_top_job import TOP_JOB_MAP as _TOP_JOB_MAP

_CHECK_INTERVAL = 60

_EXCLUDED_RANKS = {
    "Commissioner", "Commissioner-General", "Judge", "Supreme Court Judge",
    "Fire Chief", "Chief Engineer", "Bank Manager", "Funeral Director",
    "Hospital Director", "Boss", "Godfather", "Capo di tutti capi",
}

_JAIL_RANKS = {"Schooled", "Mule", "Hardrock", "Lifer"}

_MONITORED_TOP_JOBS = set(_TOP_JOB_MAP)


class AutoPromoTask(Task):
    priority = 95
    label = "Auto Promo"

    def __init__(self):
        self._last_run: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_hospital:
            return False
        is_jail_rank = state.next_rank in _JAIL_RANKS
        if state.in_jail and not is_jail_rank:
            return False
        if not state.in_jail and is_jail_rank:
            return False
        if state.in_jail and state.rank == "Lifer":
            return False
        if state.rank_progress < 100:
            return False
        if state.snipe_top_job_pending:
            return False
        if state.next_rank not in PROMO_BY_RANK:
            return False

        promo_cfg = cfg.load().get("promo", {})
        auto_on = promo_cfg.get("auto_promo", {}).get("enabled", False)
        monitor_on = promo_cfg.get("monitor_top_job", False)

        if auto_on:
            if state.next_rank in _EXCLUDED_RANKS:
                return False
        elif monitor_on and state.next_rank in _MONITORED_TOP_JOBS:
            pass
        else:
            return False

        return time.monotonic() - self._last_run >= _CHECK_INTERVAL

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_hospital:
            reasons.append("In hospital")
        is_jail_rank = state.next_rank in _JAIL_RANKS
        if state.in_jail and not is_jail_rank:
            reasons.append("In jail (non-jail rank)")
        if not state.in_jail and is_jail_rank:
            reasons.append("Not in jail (jail rank)")
        if state.in_jail and state.rank == "Lifer":
            reasons.append("Lifer rank")
        if state.rank_progress < 100:
            reasons.append(f"Rank progress {state.rank_progress}%")
        if state.snipe_top_job_pending:
            reasons.append("Snipe pending")
        if state.next_rank not in PROMO_BY_RANK:
            reasons.append("Unknown next rank")
        else:
            promo_cfg = cfg.load().get("promo", {})
            auto_on = promo_cfg.get("auto_promo", {}).get("enabled", False)
            monitor_on = promo_cfg.get("monitor_top_job", False)
            if auto_on:
                if state.next_rank in _EXCLUDED_RANKS:
                    reasons.append("Excluded rank")
            elif not (monitor_on and state.next_rank in _MONITORED_TOP_JOBS):
                reasons.append("Not enabled")
        remaining = _CHECK_INTERVAL - (time.monotonic() - self._last_run)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining)}s)")
        return reasons

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()

        landing = "/jail/jail.asp" if state.next_rank in _JAIL_RANKS else "/main.asp"
        try:
            html = browser.navigate(urls.BASE_URL + landing)
            parse_state(html, browser.current_url(), state)
        except Exception as e:
            state.add_log(f"AutoPromo: nav error: {e}")
