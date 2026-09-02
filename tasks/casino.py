"""
Casino task — plays the configured Beirut casino activity (Slots or Blackjack).
Optionally auto-travels to Beirut first if not already there.
"""

import json
import time
from pathlib import Path
from tasks.base import Task, Action
from state import GameState

_CASINO_DATA_FILE = "casino_data.json"


def _data_path() -> Path:
    from paths import data_dir
    return Path(data_dir()) / _CASINO_DATA_FILE


def load_casino_release_at() -> float:
    """Return the Unix timestamp at which casino play is allowed again, or 0 if not locked out."""
    p = _data_path()
    if p.exists():
        try:
            return float(json.loads(p.read_text(encoding="utf-8")).get("release_at", 0))
        except Exception:
            pass
    return 0.0


def save_casino_release_at(ts: float):
    p = _data_path()
    p.write_text(json.dumps({"release_at": ts}), encoding="utf-8")


class CasinoTask(Task):
    priority = 50
    label = "Casino"
    changes_city = True  # auto-travel path (config-gated); paused with the rest of the task while a crime tab is active

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        import config as cfg
        casino_cfg = cfg.load().get("casino", {})
        if not casino_cfg.get("enabled", False):
            return False
        if state.current_city.lower() != "beirut":
            # When smart travel is on, the director handles positioning — the casino
            # task only runs the activity once already in Beirut.
            if cfg.load().get("smart_travel", {}).get("enabled", False):
                return False
            if not casino_cfg.get("auto_travel", False):
                return False
            # Don't keep retrying auto-travel while warrants block it
            import executor
            if executor.travel_warrant_cooldown_active():
                return False
        return time.time() >= load_casino_release_at()

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        import config as cfg
        casino_cfg = cfg.load().get("casino", {})
        if not casino_cfg.get("enabled", False):
            reasons.append("Not enabled")
        elif state.current_city.lower() != "beirut":
            if cfg.load().get("smart_travel", {}).get("enabled", False):
                reasons.append("Not in Beirut (smart travel)")
            elif not casino_cfg.get("auto_travel", False):
                reasons.append("Not in Beirut")
            else:
                import executor
                if executor.travel_warrant_cooldown_active():
                    reasons.append("Warrant travel cooldown")
        release_at = load_casino_release_at()
        if time.time() < release_at:
            remaining = (release_at - time.time()) / 60
            reasons.append(f"Release cooldown ({int(remaining)}m)")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("play_casino"), state)
