"""
Smart Travel task — when enabled and the travel timer is free, asks the smart
travel director which city to be in and issues the travel. Positions the bot;
the gym/casino/store tasks do the actual activity once it's in the right city.
"""

import time

import config as cfg
import smart_travel as director
from tasks.base import Task, Action
from state import GameState
from tasks.gym import load_last_gym_use
from tasks.casino import load_casino_release_at

_POLL_INTERVAL = 20  # seconds between director evaluations


def _travel_free(state: GameState) -> bool:
    # Treat a missing travel-timer entry as free (the game only shows it on cooldown).
    return ("travel" not in state.timers) or state.timer_ready("travel")


class SmartTravelTask(Task):
    priority = 45  # below gym (55)/casino (50) so activities run first when in-city
    label = "Smart Travel"

    def __init__(self):
        self._last: float = 0.0

    def can_run(self, state: GameState) -> bool:
        # Only positions the bot; actual travel is issued in run() when the travel
        # timer is free.
        if not cfg.load().get("smart_travel", {}).get("enabled", False):
            return False
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.hold_action_timer:
            return False
        # Travel guard: don't leave a city that still has lawyer cases to defend
        c = cfg.load()
        law_cfg = c.get("case_work", {}).get("law", {})
        if (law_cfg.get("travel_guard", False)
                and state.occupation == "Lawyer"
                and state.current_city
                and any(city.lower() == state.current_city.lower()
                        for city in state.lawyer_cases_by_city
                        if state.lawyer_cases_by_city[city])):
            return False
        # Don't churn while travel is blocked by an outstanding-warrant cooldown —
        # every attempt would just be rejected and block other tasks.
        from executor import travel_warrant_cooldown_active, no_vehicle_cooldown_active
        if travel_warrant_cooldown_active():
            return False
        if no_vehicle_cooldown_active():
            return False
        return time.monotonic() - self._last >= _POLL_INTERVAL

    def blocked_reasons(self, state):
        reasons = []
        if not cfg.load().get("smart_travel", {}).get("enabled", False):
            reasons.append("Not enabled")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        c = cfg.load()
        law_cfg = c.get("case_work", {}).get("law", {})
        if (law_cfg.get("travel_guard", False)
                and state.occupation == "Lawyer"
                and state.current_city
                and any(city.lower() == state.current_city.lower()
                        for city in state.lawyer_cases_by_city
                        if state.lawyer_cases_by_city[city])):
            reasons.append("Lawyer travel guard (cases in city)")
        from executor import travel_warrant_cooldown_active, no_vehicle_cooldown_active
        if travel_warrant_cooldown_active():
            reasons.append("Warrant travel cooldown")
        if no_vehicle_cooldown_active():
            reasons.append("No vehicle cooldown")
        remaining = _POLL_INTERVAL - (time.monotonic() - self._last)
        if remaining > 0:
            reasons.append(f"Poll interval ({int(remaining)}s)")
        return reasons

    def _build_ctx(self, state: GameState, c: dict) -> dict:
        return {
            "now_ts": time.time(),
            "ingame_mins": state.ingame_mins,
            "current_city": state.current_city or "",
            "home_city": state.home_city or "",
            "smart": c.get("smart_travel", {}),
            "bionics": c.get("bionics", {}),
            "weapon": c.get("weapon_store", {}),
            "gym": c.get("gym", {}),
            "casino": c.get("casino", {}),
            "last_gym_use": load_last_gym_use(),
            "casino_release_at": load_casino_release_at(),
            "lawyer_cases_by_city": state.lawyer_cases_by_city,
            "law_auto_travel": c.get("case_work", {}).get("law", {}).get("auto_travel", False),
        }

    def _try_travel_expert(self, state: GameState, executor) -> bool:
        from tasks.skills_task import SKILL_IDS
        c = cfg.load()
        te = c.get("skills", {}).get("travel_expert", {})
        if not te.get("enabled", False):
            return False
        if SKILL_IDS["travel_expert"] not in state.available_skills:
            return False
        if not state.timer_ready("skill"):
            return False
        t = state.timers.get("travel", {})
        end = t.get("end")
        if not end:
            return False
        now = state._estimated_server_time()
        if now is None:
            return False
        remaining = (end - now).total_seconds()
        threshold_mins = te.get("travel_timer_threshold", 2)
        threshold_secs = threshold_mins * 60
        if remaining < threshold_secs:
            return False
        target = te.get("target", "").strip() or state.own_name
        state.add_log(f"Travel Expert: travel timer has {int(remaining // 60)}m left (threshold {threshold_mins}m), using skill on {target}.")
        executor.execute(Action(
            "use_skill",
            skill_id=SKILL_IDS["travel_expert"],
            target=target,
            skill_name="Travel Expert",
        ), state)
        return True

    def run(self, state: GameState, executor):
        self._last = time.monotonic()

        if not _travel_free(state):
            self._try_travel_expert(state, executor)
            return
        c = cfg.load()
        plan = director.decide_target_city(self._build_ctx(state, c))
        if plan.get("stay") or not plan.get("target"):
            return
        state.add_log(f"Smart travel: {plan['reason']} → travelling to {plan['target']}.")
        executor.execute(Action("travel", target_city=plan["target"], method="own_vehicle"), state)
