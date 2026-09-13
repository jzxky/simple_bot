"""
URL-based promotion page handler.

Detects when the bot is on a promotion URL and submits the configured A/B
choice. This catches promotions triggered by any navigation — including
first-rank promotions where rank_progress reads as unknown.

Respects excluded ranks and snipe_top_job_pending. Also acts as a fallback
for the sniper when top-job monitoring is on but auto-promo is off.

Priority 91 — above CrossroadTask (90) and below AutoPromoTask (95) so it
runs after auto-promo navigates to main.asp but before lower tasks navigate
away from the promo page.
"""

import config as cfg
import browser
from state import GameState, parse_state
from tasks.base import Task
from promotions import match_url, get_choice
from tasks.auto_promo import _EXCLUDED_RANKS, _MONITORED_TOP_JOBS


class PromoPageTask(Task):
    priority = 91
    label = "Promo Page"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in:
            return False

        promo = match_url(browser.current_url() or "")
        if not promo:
            return False

        if state.snipe_top_job_pending:
            return False

        promo_cfg = cfg.load().get("promo", {})
        auto_on = promo_cfg.get("auto_promo", {}).get("enabled", False)
        monitor_on = promo_cfg.get("monitor_top_job", False)

        if auto_on:
            if promo["rank"] in _EXCLUDED_RANKS:
                return False
        elif monitor_on and promo["rank"] in _MONITORED_TOP_JOBS:
            pass
        else:
            return False

        return True

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")

        promo = match_url(browser.current_url() or "")
        if not promo:
            reasons.append("Not on a promotion page")
        else:
            if state.snipe_top_job_pending:
                reasons.append("Snipe pending")

            promo_cfg = cfg.load().get("promo", {})
            auto_on = promo_cfg.get("auto_promo", {}).get("enabled", False)
            monitor_on = promo_cfg.get("monitor_top_job", False)

            if auto_on:
                if promo["rank"] in _EXCLUDED_RANKS:
                    reasons.append("Excluded rank")
            elif not (monitor_on and promo["rank"] in _MONITORED_TOP_JOBS):
                reasons.append("Not enabled")

        return reasons

    def run(self, state: GameState, executor):
        promo = match_url(browser.current_url() or "")
        if not promo:
            return

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
            msg = f"Auto-promo: {promo['rank']} — option {choice} ({option_label}) submitted."
            state.add_log(msg)
            if cfg.load().get("notifications", {}).get("auto_promo", False):
                state.push_notification("auto_promo", msg)
        except Exception as e:
            state.add_log(f"PromoPage: submit error: {e}")
