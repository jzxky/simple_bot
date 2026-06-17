"""
Respect task — fetches the player's respect % from their profile page once per day.
"""

import json
import time
from pathlib import Path
from tasks.base import Task, Action
from state import GameState

_RESPECT_COOLDOWN_HOURS = 24
_RESPECT_DATA_FILE = "respect_data.json"


def _data_path() -> Path:
    from paths import data_dir
    return Path(data_dir()) / _RESPECT_DATA_FILE


def load_respect_data() -> dict:
    p = _data_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"respect_pct": None, "last_check": 0.0}


def save_respect_data(pct: "str | None", ts: float):
    _data_path().write_text(
        json.dumps({"respect_pct": pct, "last_check": ts}), encoding="utf-8"
    )


class RespectTask(Task):
    priority = 20
    label = "Respect"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if not state.own_name:
            return False
        elapsed = (time.time() - load_respect_data().get("last_check", 0.0)) / 3600
        return elapsed >= _RESPECT_COOLDOWN_HOURS

    def run(self, state: GameState, executor):
        executor.execute(Action("fetch_respect"), state)
