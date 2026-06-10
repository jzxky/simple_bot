import time
import config as cfg
from tasks.base import Task, Action
from state import GameState

_INTERVAL = 30 * 60  # seconds


class MaintainCashTask(Task):
    priority = 25
    label = 'Maintain Cash'

    def __init__(self):
        self._last_run: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        if time.time() - self._last_run < _INTERVAL:
            return False
        min_cash = int(cfg.load().get("misc", {}).get("min_cash_on_hand", 0))
        if min_cash == 0:
            return False
        if state.clean_money > min_cash:
            return True
        if state.clean_money < min_cash and state.bank_balance > 0:
            return True
        return False

    def run(self, state: GameState, executor):
        min_cash = int(cfg.load().get("misc", {}).get("min_cash_on_hand", 0))
        if state.clean_money > min_cash:
            executor.execute(Action("deposit", min_cash_on_hand=min_cash), state)
        elif state.clean_money < min_cash:
            shortfall = min_cash - state.clean_money
            withdraw = min(shortfall, state.bank_balance)
            if withdraw > 0:
                executor.execute(Action("withdraw", amount=withdraw), state)
        self._last_run = time.time()
