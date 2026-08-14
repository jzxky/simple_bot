"""
Event Boss task.

During a boss event the game shows an "Event" timer in the user timer bar and
an ATTACK! link on /conflict/bossevent.asp. This task visits the boss page,
follows the attack link (its id changes over time, so we match on
action=attack rather than the exact URL), and logs the success/fail result.

If the attack link isn't present the boss is assumed to be mid-respawn and the
task holds for 5 minutes before checking again.
"""

import time

import config as cfg
from tasks.base import Task, Action
from state import GameState

HOLD_SECONDS = 5 * 60   # respawn hold when no attack link is available
POLL_SECONDS = 30       # minimum gap between boss-page checks while the event is live


class EventBossTask(Task):
    priority = 60
    label = "Event Boss"

    def __init__(self):
        self._hold_until: float = 0.0
        self._last_run: float = 0.0

    def _event_available(self, state: GameState) -> bool:
        """True if a boss-event timer is present and ready in the timer bar."""
        for name, _t in (state.timers or {}).items():
            if "event" in name.lower():
                return state.timer_ready(name)
        return False

    def can_run(self, state: GameState) -> bool:
        # Guards: task enabled in config, logged in, not in jail, event timer available.
        if not cfg.load().get("event_boss", {}).get("enabled", False):
            return False
        if not state.logged_in or state.in_jail:
            return False
        now = time.monotonic()
        if now < self._hold_until:
            return False
        if now - self._last_run < POLL_SECONDS:
            return False
        return self._event_available(state)

    def blocked_reasons(self, state):
        reasons = []
        if not cfg.load().get("event_boss", {}).get("enabled", False):
            reasons.append("Not enabled")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        now = time.monotonic()
        if now < self._hold_until:
            reasons.append(f"Hold ({int(self._hold_until - now)}s)")
        if now - self._last_run < POLL_SECONDS:
            reasons.append(f"Poll cooldown ({int(POLL_SECONDS - (now - self._last_run))}s)")
        if not self._event_available(state):
            reasons.append("Event timer not ready")
        return reasons

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()
        state._event_boss_hold = False
        executor.execute(Action("event_boss"), state)
        # Handler sets _event_boss_hold when the boss is respawning (no attack link).
        if getattr(state, "_event_boss_hold", False):
            state._event_boss_hold = False
            self._hold_until = time.monotonic() + HOLD_SECONDS
