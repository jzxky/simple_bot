"""
Enrols in a training centre course (Jui Jitsu, Muay Thai, Karate, or MMA).
"""

import config as cfg
import urls
from tasks.base import Task, Action
from state import GameState
from action_cooldowns import ACTION_COOLDOWNS, should_skip_action_for_armed_robbery

TRAINING_PATH = "/localcity/training.asp"

TRAINING_COSTS = {
    "Jui Jitsu": 250_000,
    "Muay Thai": 250_000,
    "Karate":    250_000,
    "MMA":       400_000,
}


class TrainingCentreTask(Task):
    priority = 60
    label = "Training Centre"

    def __init__(self, discipline: str):
        self.discipline = discipline

    def can_run(self, state: GameState) -> bool:
        if not cfg.load().get("action", {}).get("enabled", False):
            return False
        if not (state.logged_in and not state.in_jail and state.action_available()
                and state.in_home_city() and not state.hold_action_timer):
            return False
        return not should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["training_centre"])

    def blocked_reasons(self, state):
        reasons = []
        if not cfg.load().get("action", {}).get("enabled", False):
            reasons.append("Not enabled")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if not state.action_available():
            reasons.append("Action timer busy")
        if not state.in_home_city():
            reasons.append("Not in home city")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if should_skip_action_for_armed_robbery(state, ACTION_COOLDOWNS["training_centre"]):
            reasons.append("Waiting for armed robbery")
        return reasons

    def run(self, state: GameState, executor):
        if self.discipline not in TRAINING_COSTS:
            state.add_log(f"Training centre: unknown discipline '{self.discipline}'.")
            return
        url = urls.BASE_URL + TRAINING_PATH
        executor.execute(Action("do_training_centre", url=url, discipline=self.discipline), state)
