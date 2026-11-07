"""
Skill tasks — discover available skills on startup, then auto-use
Combat Medic, Biometric Virus, and All Seeing Eye when configured.
Travel Expert is integrated into SmartTravelTask instead.
"""

import time
import config as cfg
from tasks.base import Task, Action
from state import GameState


_rediscover_flag = False


def request_skill_rediscover():
    global _rediscover_flag
    _rediscover_flag = True


SKILL_IDS = {
    "combat_medic": "skill_combatmedic",
    "biometric_virus": "skill_destroybionics",
    "travel_expert": "skill_jetsetter",
    "all_seeing_eye": "skill_allseeingeye",
    "news_editor": "skill_newseditor",
}


_REDISCOVER_COOLDOWN = 24 * 60 * 60


class DiscoverSkillsTask(Task):
    priority = 90
    label = "Discover Skills"

    def __init__(self):
        self._discovered = False
        self._last_run_time: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if self._discovered:
            if not _rediscover_flag:
                return False
            if time.monotonic() - self._last_run_time < _REDISCOVER_COOLDOWN:
                return False
        return state.logged_in and not state.in_jail and not state.in_hospital

    def blocked_reasons(self, state):
        reasons = []
        if self._discovered and not _rediscover_flag:
            reasons.append("Already discovered")
        elif self._discovered and _rediscover_flag:
            remaining = _REDISCOVER_COOLDOWN - (time.monotonic() - self._last_run_time)
            if remaining > 0:
                reasons.append(f"Cooldown ({int(remaining // 3600)}h left)")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        return reasons

    def run(self, state: GameState, executor):
        global _rediscover_flag
        self._discovered = True
        self._last_run_time = time.monotonic()
        _rediscover_flag = False
        executor.execute(Action("discover_skills"), state)


class CombatMedicTask(Task):
    priority = 30
    label = "Combat Medic"

    def can_run(self, state: GameState) -> bool:
        c = cfg.load().get("skills", {}).get("combat_medic", {})
        if not c.get("target", "").strip():
            return False
        if SKILL_IDS["combat_medic"] not in state.available_skills:
            return False
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.hold_action_timer:
            return False
        if state.agg_pro_active:
            return False
        return state.timer_ready("skill")

    def blocked_reasons(self, state):
        reasons = []
        c = cfg.load().get("skills", {}).get("combat_medic", {})
        if not c.get("target", "").strip():
            reasons.append("No target set")
        if SKILL_IDS["combat_medic"] not in state.available_skills:
            reasons.append("Skill not unlocked")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if state.agg_pro_active:
            reasons.append("Protection active")
        if not state.timer_ready("skill"):
            reasons.append("Skill timer not ready")
        return reasons

    def run(self, state: GameState, executor):
        c = cfg.load().get("skills", {}).get("combat_medic", {})
        executor.execute(Action(
            "use_skill",
            skill_id=SKILL_IDS["combat_medic"],
            target=c["target"].strip(),
            skill_name="Combat Medic",
        ), state)


class BiometricVirusTask(Task):
    priority = 30
    label = "Biometric Virus"

    def can_run(self, state: GameState) -> bool:
        c = cfg.load().get("skills", {}).get("biometric_virus", {})
        if not c.get("target", "").strip():
            return False
        if SKILL_IDS["biometric_virus"] not in state.available_skills:
            return False
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.hold_action_timer:
            return False
        if state.agg_pro_active:
            return False
        return state.timer_ready("skill")

    def blocked_reasons(self, state):
        reasons = []
        c = cfg.load().get("skills", {}).get("biometric_virus", {})
        if not c.get("target", "").strip():
            reasons.append("No target set")
        if SKILL_IDS["biometric_virus"] not in state.available_skills:
            reasons.append("Skill not unlocked")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if state.agg_pro_active:
            reasons.append("Protection active")
        if not state.timer_ready("skill"):
            reasons.append("Skill timer not ready")
        return reasons

    def run(self, state: GameState, executor):
        c = cfg.load().get("skills", {}).get("biometric_virus", {})
        executor.execute(Action(
            "use_skill",
            skill_id=SKILL_IDS["biometric_virus"],
            target=c["target"].strip(),
            skill_name="Biometric Virus",
        ), state)


class AllSeeingEyeTask(Task):
    """Auto Respect Check: All Seeing Eye on Player Hub's respect targets.
    Needs the hub; targets are the hub's list, the first viable one in the
    bot's city."""
    priority = 25
    label = "All Seeing Eye"

    _HUB_RETRY_SECONDS = 10 * 60   # hub unreachable
    _NO_TARGET_REST_SECONDS = 30 * 60  # no target in this city (or all were elsewhere)
    _JAILED_TARGET_COOLDOWN = 30 * 60  # target was dead/in jail when we tried

    def __init__(self):
        self._hub_retry_at: float = 0.0
        self._target_cooldown: dict = {}  # username -> monotonic time it's usable again

    @staticmethod
    def _hub_mode() -> bool:
        import sync_client
        return bool(sync_client.hub_url())

    def can_run(self, state: GameState) -> bool:
        c = cfg.load().get("skills", {}).get("all_seeing_eye", {})
        if not c.get("enabled", False) or not self._hub_mode():
            return False
        if time.monotonic() < self._hub_retry_at:
            return False
        if SKILL_IDS["all_seeing_eye"] not in state.available_skills:
            return False
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.hold_action_timer:
            return False
        return state.timer_ready("skill")

    def blocked_reasons(self, state):
        reasons = []
        c = cfg.load().get("skills", {}).get("all_seeing_eye", {})
        if not c.get("enabled", False):
            reasons.append("Not enabled")
        if not self._hub_mode():
            reasons.append("Not connected to Player Hub")
        if time.monotonic() < self._hub_retry_at:
            reasons.append(f"Resting — no hub target in city ({int((self._hub_retry_at - time.monotonic()) // 60)}m)")
        if SKILL_IDS["all_seeing_eye"] not in state.available_skills:
            reasons.append("Skill not unlocked")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if not state.timer_ready("skill"):
            reasons.append("Skill timer not ready")
        return reasons

    def run(self, state: GameState, executor):
        self._run_hub(state, executor)

    def _run_hub(self, state: GameState, executor):
        import sync_client
        try:
            targets = sync_client.respect_targets()
        except Exception as e:
            state.add_log(f"All Seeing Eye: could not fetch hub targets: {e}")
            self._hub_retry_at = time.monotonic() + self._HUB_RETRY_SECONDS
            return
        # A target only has to be in this city, not online: the hub's
        # current_city is the last city each player was seen in, and anyone in
        # this city's active list right now counts too.
        city = state.current_city
        local = state.local_players
        in_city = [t for t in targets
                   if t["username"] in local or (city and t.get("current_city") == city)]
        # Skip targets currently flagged in jail on the online list, and any
        # that recently failed with "must be alive and not in jail".
        now = time.monotonic()
        self._target_cooldown = {u: t for u, t in self._target_cooldown.items() if t > now}
        jailed_now = state.jail_players or set()
        in_city = [t for t in in_city
                   if t["username"] not in jailed_now
                   and t["username"] not in self._target_cooldown]
        elsewhere = 0
        jailed = 0
        for t in in_city:
            claim_id = sync_client.respect_claim(t["username"])
            if claim_id is None:
                continue
            state.last_skill_result = {}
            executor.execute(Action(
                "use_skill",
                skill_id=SKILL_IDS["all_seeing_eye"],
                target=t["username"],
                skill_name="All Seeing Eye",
                update_respect=True,
                respect_claim_id=claim_id,
            ), state)
            result = state.last_skill_result
            if result.get("out_of_city"):
                elsewhere += 1  # hub's city was stale; try the next viable target
                continue
            if result.get("target_jailed"):
                jailed += 1
                self._target_cooldown[t["username"]] = (
                    time.monotonic() + self._JAILED_TARGET_COOLDOWN)
                state.add_log(f"All Seeing Eye: {t['username']} is in jail or dead — "
                              f"skipping them for 30 minutes.")
                continue
            return  # used, or failed for another reason (timer, page error)
        if elsewhere or jailed:
            state.add_log(f"All Seeing Eye: {elsewhere} target(s) weren't in {city}, "
                          f"{jailed} in jail/dead; "
                          f"no other target here — resting 30 minutes.")
        else:
            state.add_log(f"All Seeing Eye: no hub target in {city or 'unknown city'} "
                          f"({len(targets)} viable elsewhere) — resting 30 minutes.")
        self._hub_retry_at = time.monotonic() + self._NO_TARGET_REST_SECONDS


class NewsEditorTask(Task):
    priority = 30
    label = "News Editor"

    def can_run(self, state: GameState) -> bool:
        c = cfg.load().get("skills", {}).get("news_editor", {})
        if not c.get("target", "").strip():
            return False
        if not c.get("title", "").strip():
            return False
        if not c.get("event", "").strip():
            return False
        if SKILL_IDS["news_editor"] not in state.available_skills:
            return False
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.hold_action_timer:
            return False
        return state.timer_ready("skill")

    def blocked_reasons(self, state):
        reasons = []
        c = cfg.load().get("skills", {}).get("news_editor", {})
        if not c.get("target", "").strip():
            reasons.append("No target set")
        if not c.get("title", "").strip():
            reasons.append("No title set")
        if not c.get("event", "").strip():
            reasons.append("No event set")
        if SKILL_IDS["news_editor"] not in state.available_skills:
            reasons.append("Skill not unlocked")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if not state.timer_ready("skill"):
            reasons.append("Skill timer not ready")
        return reasons

    def run(self, state: GameState, executor):
        c = cfg.load().get("skills", {}).get("news_editor", {})
        executor.execute(Action(
            "use_news_editor",
            skill_id=SKILL_IDS["news_editor"],
            target=c["target"].strip(),
            title=c["title"].strip(),
            event=c["event"].strip(),
            skill_name="News Editor",
        ), state)
