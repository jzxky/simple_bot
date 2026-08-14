"""
Blind eye task — process the blind eye queue by selecting gangsters on the
blind eye page and submitting the form.
"""

import config as cfg
from tasks.base import Task, Action
from state import GameState


class BlindEyeTask(Task):
    priority = 4
    label = "Blind Eye"

    def can_run(self, state: GameState) -> bool:
        return (
            state.logged_in
            and not state.in_jail
            and state.in_home_city()
            and state.timer_ready("traffick")
            and len(cfg.blind_eye_queue_peek()) > 0
        )

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if not state.in_home_city():
            reasons.append("Not in home city")
        if not state.timer_ready("traffick"):
            reasons.append("Traffick timer not ready")
        if len(cfg.blind_eye_queue_peek()) == 0:
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("do_blind_eye"), state)
