"""
Performs the configured away-from-home-city action when the action timer is ready.
Supported types: drug_manufacturing, community_service, dog_trains.
"""

from tasks.base import Task, Action
from state import GameState
from action_cooldowns import ACTION_COOLDOWNS, should_skip_action_for_armed_robbery


_CS_AWAY_ALLOWED_RANKS = {
    "loan officer", "bank manager", "mortician", "undertaker", "funeral director",
    "doctor", "surgeon", "hospital director", "technician", "engineer",
    "chief engineer", "supervisor", "superintendent", "commissioner-general",
    "lawyer", "judge", "supreme court judge", "sergeant", "senior sergeant",
    "detective", "commissioner", "fire fighter", "fire chief", "mayor",
}


class AwayActionTask(Task):
    priority = 60
    label = 'Away Action'

    def __init__(self, action_type: str):
        self.action_type = action_type

    def can_run(self, state: GameState) -> bool:
        if not self.action_type:
            return False
        if not (state.logged_in and not state.in_jail and state.action_available()
                and not state.in_home_city() and not state.hold_action_timer):
            return False
        if self.action_type == "community_service":
            rank_lower = (state.rank or "").lower()
            occ_lower = (state.occupation or "").lower()
            if rank_lower not in _CS_AWAY_ALLOWED_RANKS and occ_lower not in _CS_AWAY_ALLOWED_RANKS:
                return False
        if self.action_type == "drug_manufacturing":
            import executor
            if executor.drug_manufacture_cooldown_active():
                return False
        cooldown_key = "community_service_away" if self.action_type == "community_service" else self.action_type
        cooldown = ACTION_COOLDOWNS.get(cooldown_key, 10)
        return not should_skip_action_for_armed_robbery(state, cooldown)

    def blocked_reasons(self, state):
        reasons = []
        if not self.action_type:
            reasons.append("No action type")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if not state.action_available():
            reasons.append("Action timer busy")
        if state.in_home_city():
            reasons.append("In home city")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if self.action_type == "community_service":
            rank_lower = (state.rank or "").lower()
            occ_lower = (state.occupation or "").lower()
            if rank_lower not in _CS_AWAY_ALLOWED_RANKS and occ_lower not in _CS_AWAY_ALLOWED_RANKS:
                reasons.append("Rank/occupation not allowed")
        if self.action_type == "drug_manufacturing":
            import executor
            if executor.drug_manufacture_cooldown_active():
                reasons.append("Manufacture cooldown")
        if self.action_type:
            cooldown_key = "community_service_away" if self.action_type == "community_service" else self.action_type
            cooldown = ACTION_COOLDOWNS.get(cooldown_key, 10)
            if should_skip_action_for_armed_robbery(state, cooldown):
                reasons.append("Waiting for armed robbery")
        return reasons

    def run(self, state: GameState, executor):
        if self.action_type == "community_service":
            executor.execute(Action("do_community_service", in_home_city=False), state)
        elif self.action_type == "drug_manufacturing":
            executor.execute(Action("do_drug_manufacturing"), state)
        elif self.action_type == "dog_trains":
            executor.execute(Action("do_dog_trains", context="away"), state)
        else:
            state.add_log(f"Unknown away action type: {self.action_type}")
