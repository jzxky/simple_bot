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

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        import config as cfg
        casino_cfg = cfg.load().get("casino", {})
        if not casino_cfg.get("enabled", False):
            return False
        if state.current_city.lower() != "beirut" and not casino_cfg.get("auto_travel", False):
            return False
        return time.time() >= load_casino_release_at()

    def run(self, state: GameState, executor):
        executor.execute(Action("play_casino"), state)
