"""
Checks the Auckland drug store for wanted items and purchases them.

Runs when: logged in, not in jail/hospital, in Auckland, enabled in config,
enough wall-clock time has passed since last check, and not in post-purchase
cooldown (30 minutes after a successful buy).

Only three items are relevant: Pseudoephedrine, Epipen, Medipack.
Purchase order follows config priority_order; if empty, uses wanted order.
"""

import time
from tasks.base import Task, Action
from state import GameState


def load_drug_store_state() -> dict:
    import config as cfg
    return cfg.load().get("drug_store_state", {})


def save_drug_store_state(updates: dict):
    import config as cfg
    c = cfg.load()
    c.setdefault("drug_store_state", {}).update(updates)
    cfg.save(c)


class DrugStoreTask(Task):
    priority = 53
    label = "Drug Store"

    def __init__(self):
        s = load_drug_store_state()
        self.last_checked_at: float = float(s.get("last_checked_at", 0))
        self.last_stock: dict = s.get("last_stock", {})
        self.purchase_cooldown_until: float = float(s.get("purchase_cooldown_until", 0))

    def _interval_secs(self) -> int:
        import config as cfg
        d = cfg.load().get("drug_store", {})
        return max(1, int(d.get("check_interval_minutes", 5)) * 60
                   + int(d.get("check_interval_seconds", 0)))

    def can_run(self, state: GameState) -> bool:
        import config as cfg
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.current_city.lower() != "auckland":
            return False
        d = cfg.load().get("drug_store", {})
        if not d.get("enabled", False):
            return False
        now = time.time()
        if self.purchase_cooldown_until > now:
            return False
        interval = self._interval_secs()
        if self.last_checked_at > 0 and now - self.last_checked_at < interval:
            return False
        return True

    def blocked_reasons(self, state):
        import config as cfg
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.current_city.lower() != "auckland":
            reasons.append("Not in Auckland")
        d = cfg.load().get("drug_store", {})
        if not d.get("enabled", False):
            reasons.append("Not enabled")
        else:
            now = time.time()
            if self.purchase_cooldown_until > now:
                remaining = int(self.purchase_cooldown_until - now)
                reasons.append(f"Purchase cooldown ({remaining}s)")
            else:
                interval = self._interval_secs()
                if self.last_checked_at > 0:
                    remaining = interval - (now - self.last_checked_at)
                    if remaining > 0:
                        reasons.append(f"Interval ({int(remaining)}s)")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("check_drug_store", _task=self), state)
