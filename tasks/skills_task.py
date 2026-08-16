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


class DiscoverSkillsTask(Task):
    priority = 90
    label = "Discover Skills"

    def __init__(self):
        self._discovered = False

    def can_run(self, state: GameState) -> bool:
        if self._discovered and not _rediscover_flag:
            return False
        return state.logged_in and not state.in_jail and not state.in_hospital

    def blocked_reasons(self, state):
        reasons = []
        if self._discovered and not _rediscover_flag:
            reasons.append("Already discovered")
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
    priority = 25
    label = "All Seeing Eye"

    def can_run(self, state: GameState) -> bool:
        c = cfg.load().get("skills", {}).get("all_seeing_eye", {})
        if not c.get("enabled", False):
            return False
        if not c.get("group", "").strip():
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
        elif not c.get("group", "").strip():
            reasons.append("No group set")
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
        import player_db
        c = cfg.load().get("skills", {}).get("all_seeing_eye", {})
        group = c["group"].strip()
        players = player_db.get_players_by_group(group)
        if not players:
            state.add_log(f"All Seeing Eye: no players in group '{group}'.")
            return
        oldest = min(players, key=lambda p: p.get("respect_last_checked", 0) or 0)
        executor.execute(Action(
            "use_skill",
            skill_id=SKILL_IDS["all_seeing_eye"],
            target=oldest["username"],
            skill_name="All Seeing Eye",
            update_respect=True,
        ), state)


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
