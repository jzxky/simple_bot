import time
import config as cfg
from tasks.base import Task, Action
from state import GameState

_INTERVAL = 30 * 60  # seconds


def _min_cash(state: GameState) -> int:
    """Configured min cash on hand, raised to the drug store's $1M floor while
    that task is active (enabled + in Auckland) so its cash reserve isn't
    deposited straight back. 0 (disabled) stays 0."""
    from tasks.drug_store import drug_store_active, DRUG_STORE_CASH_FLOOR
    min_cash = int(cfg.load().get("misc", {}).get("min_cash_on_hand", 0))
    if min_cash and drug_store_active(state):
        return max(min_cash, DRUG_STORE_CASH_FLOOR)
    return min_cash


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
        min_cash = _min_cash(state)
        if min_cash == 0:
            return False
        if state.clean_money > min_cash:
            return True
        if state.clean_money < min_cash and state.bank_balance > 0:
            return True
        return False

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        remaining = _INTERVAL - (time.time() - self._last_run)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining // 60)}m)")
        min_cash = _min_cash(state)
        if min_cash == 0:
            reasons.append("No min cash configured")
        elif not (state.clean_money > min_cash or (state.clean_money < min_cash and state.bank_balance > 0)):
            reasons.append("Cash at target level")
        return reasons

    def run(self, state: GameState, executor):
        min_cash = _min_cash(state)
        if state.clean_money > min_cash:
            executor.execute(Action("deposit", min_cash_on_hand=min_cash), state)
        elif state.clean_money < min_cash:
            shortfall = min_cash - state.clean_money
            withdraw = min(shortfall, state.bank_balance)
            if withdraw > 0:
                executor.execute(Action("withdraw", amount=withdraw), state)
        self._last_run = time.time()
