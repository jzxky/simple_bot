"""
Gym task — visits the gym every 12 hours to perform the configured activity.
Optionally auto-travels to Chicago first if not already there.
"""

import json
import time
from pathlib import Path
from tasks.base import Task, Action
from state import GameState

_GYM_COOLDOWN_HOURS = 12
_GYM_DATA_FILE = "gym_data.json"


def _data_path() -> Path:
    from paths import data_dir
    return Path(data_dir()) / _GYM_DATA_FILE


def load_last_gym_use() -> float:
    """Return the Unix timestamp of the last gym use, or 0 if never."""
    p = _data_path()
    if p.exists():
        try:
            return float(json.loads(p.read_text(encoding="utf-8")).get("last_gym_use", 0))
        except Exception:
            pass
    return 0.0


def save_last_gym_use(ts: float):
    p = _data_path()
    p.write_text(json.dumps({"last_gym_use": ts}), encoding="utf-8")


class GymTask(Task):
    priority = 55
    label = "Gym"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        import config as cfg
        gym_cfg = cfg.load().get("gym", {})
        if not gym_cfg.get("enabled", False):
            return False
        elapsed_hours = (time.time() - load_last_gym_use()) / 3600
        return elapsed_hours >= _GYM_COOLDOWN_HOURS

    def run(self, state: GameState, executor):
        executor.execute(Action("do_gym"), state)
