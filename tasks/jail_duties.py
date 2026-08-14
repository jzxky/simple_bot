import time
import config as cfg
from tasks.base import Task, Action


class JailDutiesTask(Task):
    priority = 30
    label = 'Jail Duties'

    def __init__(self):
        self._interval = 30 * 60
        self._last_fired: float = 0.0

    def can_run(self, state) -> bool:
        if not state.in_jail or not state.logged_in:
            return False
        if not cfg.load().get("jail", {}).get("enabled", False):
            return False
        duty = cfg.load().get("jail", {}).get("duty", "laundry")
        if duty in ("makeshank", "digtunnel"):
            # Manual duties are done one Work at a time; gate on the earn timer
            # (in addition to being in jail).
            return state.timer_ready("earn")
        return time.monotonic() - self._last_fired >= self._interval

    def blocked_reasons(self, state):
        reasons = []
        if not state.in_jail:
            reasons.append("Not in jail")
        if not state.logged_in:
            reasons.append("Not logged in")
        if not cfg.load().get("jail", {}).get("enabled", False):
            reasons.append("Not enabled")
        duty = cfg.load().get("jail", {}).get("duty", "laundry")
        if duty in ("makeshank", "digtunnel"):
            if not state.timer_ready("earn"):
                reasons.append("Earn timer not ready")
        else:
            remaining = self._interval - (time.monotonic() - self._last_fired)
            if remaining > 0:
                reasons.append(f"Interval ({int(remaining // 60)}m)")
        return reasons

    def run(self, state, executor):
        self._last_fired = time.monotonic()
        duty = cfg.load().get("jail", {}).get("duty", "laundry")
        executor.execute(Action("jail_duties", duty=duty), state)
