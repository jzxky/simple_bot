"""
War Mode WS monitor task.

When War Mode is enabled, periodically sweeps the opps/friendlies watch lists,
visiting each profile and parsing whacks-survived. An increase over the stored
value marks the character as whacked (handled in war_mode.record_ws).
"""

import time

import config as cfg
import war_mode
from tasks.base import Task, Action
from state import GameState


class WSMonitorTask(Task):
    priority = 20
    label = "WS Monitor"

    def __init__(self):
        self._last: float = 0.0

    def _interval(self) -> int:
        wm = cfg.load().get("war_mode", {})
        if self._is_server_mode():
            m = wm.get("server_check_interval_minutes", 5)
        else:
            m = wm.get("monitor_interval_minutes", 5)
        return max(1, int(m or 5)) * 60

    def _is_server_mode(self) -> bool:
        c = cfg.load()
        wm = c.get("war_mode", {})
        sc = c.get("sync", {})
        return (wm.get("mode") == "server"
                and sc.get("enabled") and sc.get("server_url") and sc.get("api_key"))

    def _get_names(self):
        if self._is_server_mode():
            return war_mode.all_names_from_hub()
        return war_mode.all_names()

    def can_run(self, state: GameState) -> bool:
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            return False
        if not wm.get("checking_enabled", False):
            return False
        if not state.logged_in:
            return False
        if not self._get_names():
            return False
        return time.monotonic() - self._last >= self._interval()

    def blocked_reasons(self, state):
        reasons = []
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            reasons.append("Not enabled")
        if not wm.get("checking_enabled", False):
            reasons.append("Checking disabled")
        if not state.logged_in:
            reasons.append("Not logged in")
        if not self._get_names():
            reasons.append("No watch names")
        remaining = self._interval() - (time.monotonic() - self._last)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining // 60)}m)")
        return reasons

    def run(self, state: GameState, executor):
        self._last = time.monotonic()
        if not self._is_server_mode():
            try:
                result = war_mode.sync_from_hub()
                if result is not None:
                    added, total = result
                    if added:
                        state.add_log(f"War hub: synced {added} new name(s) ({total} total).")
            except Exception as e:
                state.add_log(f"War hub sync error: {e}")
        executor.execute(Action("ws_monitor"), state)
