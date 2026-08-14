"""
Event-boss consumable task.

When event-boss handling is enabled, auto-consumes collected event items whose
per-item toggle is on and whose condition is met:
  - timer items  → the reset target timer is on cooldown
  - Fries        → energy < 100%
  - Milk         → whenever stock remains
  - Popcorn        → resets earn timer (only in manual earn mode)
  - Lightning      → unsupported (never consumed)

Stock counts come from the last bossevent.asp visit (EventBossTask); consuming
decrements the local count so we don't over-retry between visits.
"""

import queue
import time

import config as cfg
import event_consumables as _ec
from tasks.base import Task, Action
from state import GameState

_POLL = 2  # seconds between consume evaluations (matches the main loop tick)


class EventConsumeTask(Task):
    priority = 58
    label = "Event Consume"

    def __init__(self):
        self._last: float = 0.0

    def _eligible(self, state: GameState, cond) -> bool:
        kind, param = cond
        if kind == "always":
            return True
        if kind == "energy":
            # Don't top up agg energy while aggravating is throttled by fails.
            return (state.energy or 0) < 100 and state.agg_fail_count() < 3
        if kind == "timer":
            return param in state.timers and not state.timer_ready(param)
        if kind == "earn_timer":
            earn_mode = cfg.load().get("earns", {}).get("earn_mode", "auto")
            if earn_mode != "manual":
                return False
            return param in state.timers and not state.timer_ready(param)
        return False  # unsupported

    def _pick(self, state: GameState, consume_cfg: dict):
        stock = state.event_consumables or {}
        for name in _ec.EVENT_ORDER:
            _label, kind, param = _ec.INFO[name]
            if kind == "unsupported":
                continue
            if not consume_cfg.get(name, False):
                continue
            ec = stock.get(name)
            if not ec or ec.get("qty", 0) <= 0 or not ec.get("url"):
                continue
            if self._eligible(state, (kind, param)):
                return name, ec["url"]
        return None

    def can_run(self, state: GameState) -> bool:
        eb = cfg.load().get("event_boss", {})
        if not eb.get("enabled", False):
            return False
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if time.monotonic() - self._last < _POLL:
            return False
        return self._pick(state, eb.get("consume", {})) is not None

    def blocked_reasons(self, state):
        reasons = []
        eb = cfg.load().get("event_boss", {})
        if not eb.get("enabled", False):
            reasons.append("Not enabled")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        remaining = _POLL - (time.monotonic() - self._last)
        if remaining > 0:
            reasons.append(f"Poll cooldown ({int(remaining)}s)")
        if self._pick(state, eb.get("consume", {})) is None:
            reasons.append("No eligible consumable")
        return reasons

    def run(self, state: GameState, executor):
        self._last = time.monotonic()
        picked = self._pick(state, cfg.load().get("event_boss", {}).get("consume", {}))
        if not picked:
            return
        name, url = picked
        executor.execute(Action("event_consume", name=name, url=url), state)


class ManualEventConsumeTask(Task):
    priority = 59
    label = "Manual Event Consume"

    def __init__(self, eq: queue.Queue):
        self._queue = eq

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not state.in_jail and not self._queue.empty()

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        try:
            name = self._queue.get_nowait()
        except Exception:
            return
        ec = (state.event_consumables or {}).get(name)
        if not ec or not ec.get("url"):
            state.add_log(f"Event consume: no URL for {name}")
            return
        executor.execute(Action("event_consume", name=name, url=ec["url"]), state)
