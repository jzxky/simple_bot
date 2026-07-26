"""
Banking task — auto-invests money in the bank when the investment has matured.
"""

import json
import time
from pathlib import Path
from tasks.base import Task, Action
from state import GameState

_BANKING_DATA_FILE = "banking_data.json"


def _data_path() -> Path:
    from paths import data_dir
    return Path(data_dir()) / _BANKING_DATA_FILE


def load_mature_date() -> float:
    p = _data_path()
    if p.exists():
        try:
            return float(json.loads(p.read_text(encoding="utf-8")).get("mature_at", 0))
        except Exception:
            pass
    return 0.0


def save_mature_date(ts: float):
    p = _data_path()
    p.write_text(json.dumps({"mature_at": ts}), encoding="utf-8")


class BankingInvestTask(Task):
    priority = 60
    label = "Banking"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        import config as cfg
        bank_cfg = cfg.load().get("banking", {})
        if not bank_cfg.get("auto_invest_enabled", False):
            return False
        return time.time() >= load_mature_date()

    def run(self, state: GameState, executor):
        executor.execute(Action("do_bank_invest"), state)
