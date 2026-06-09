import math
import queue
import config as cfg
from tasks.base import Task, Action
from state import GameState

# Maps consumable type → timer key in state.timers
# Ecstasy is handled separately (energy-based)
CONSUMABLE_TIMER_MAP = {
    "marijuana": "case",
    "cocaine":   "earn",
    "acid":      "travel",
    "speed":     "whack",
    "pice":      "skill",
    "heroin":    "action",
}

# Energy % → minutes of regeneration elapsed (from game data)
_ENERGY_TABLE = [
    (0.0, 1), (2.0, 4), (2.7, 5), (3.3, 6), (5.0, 7), (5.8, 8),
    (6.7, 9), (7.5, 10), (8.3, 11), (9.2, 12), (13.3, 13), (15.6, 14),
    (16.7, 15), (17.8, 16), (18.9, 17), (30.0, 18), (31.7, 19),
    (33.3, 20), (35.0, 21), (36.7, 22), (38.3, 23), (53.3, 24),
    (55.6, 25), (57.8, 26), (60.0, 27), (62.2, 28), (64.4, 29), (100.0, 30),
]


def _energy_to_mins(pct: float) -> int:
    for threshold, mins in _ENERGY_TABLE:
        if pct <= threshold:
            return mins
    return 30


def _timer_limit_secs(cfg_cons: dict) -> int:
    """Parse mm:ss string → total seconds."""
    raw = cfg_cons.get("timer_limit", "00:00")
    try:
        parts = raw.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return 0


def _passes_timer_gate(consume_type: str, state: GameState, cfg_cons: dict) -> bool:
    """Return True if the consumable's timer condition allows consuming."""
    limit_secs = _timer_limit_secs(cfg_cons)
    if limit_secs == 0:
        return True

    if consume_type == "ecstasy":
        # Block auto-consume for ecstasy if agg crimes disabled
        return False

    timer_key = CONSUMABLE_TIMER_MAP.get(consume_type)
    if timer_key is None:
        return True  # unknown type — don't block

    timer = state.timers.get(timer_key, {})
    if timer.get("ready", True):
        return False  # timer already ready — no point consuming

    end = timer.get("end")
    if end is None:
        return False

    from datetime import datetime
    now = state.server_time or datetime.utcnow()
    remaining_secs = max(0, int((end - now).total_seconds()))
    return remaining_secs > limit_secs


def _ecstasy_passes_gate(state: GameState, cfg_cons: dict, agg_cfg: dict) -> bool:
    """Ecstasy gate: gap between current and threshold energy > ceil(timer_limit_mins)."""
    limit_secs = _timer_limit_secs(cfg_cons)
    if limit_secs == 0:
        return True

    limit_mins = math.floor(limit_secs / 60)

    # Pick threshold based on current city
    in_home = (state.current_city == state.home_city)
    if in_home:
        threshold_pct = float(agg_cfg.get("primary", {}).get("energy_threshold", 50))
    else:
        threshold_pct = float(agg_cfg.get("away_crime", {}).get("energy_threshold", 50))

    current_pct = state.energy if state.energy is not None else 0.0
    gap = _energy_to_mins(threshold_pct) - _energy_to_mins(current_pct)
    return gap > limit_mins


class ConsumeTask(Task):
    priority = 30

    def __init__(self, consume_queue: queue.Queue):
        self._queue = consume_queue

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in:
            return False
        c = cfg.load()
        cons_cfg = c.get("consumables", {})
        # Auto-consume has its own readiness check
        if self._auto_consume_ready(state, c, cons_cfg):
            return True
        return not self._queue.empty()

    def _auto_consume_ready(self, state: GameState, c: dict, cons_cfg: dict) -> bool:
        if not cons_cfg.get("auto_consume", False):
            return False
        auto_type = cons_cfg.get("auto_consumable", "")
        if not auto_type:
            return False
        if state.consumables.get(auto_type, 0) <= 0:
            return False
        limit = int(cons_cfg.get("consumable_limit", 33))
        buffer_ = int(cons_cfg.get("buffer", 0))
        if (state.consumables_24h or 0) >= (limit - buffer_):
            return False
        if auto_type == "ecstasy":
            agg_cfg = c.get("aggravated_crimes", {})
            if not agg_cfg.get("enabled", False):
                return False
            return _ecstasy_passes_gate(state, cons_cfg, agg_cfg)
        return _passes_timer_gate(auto_type, state, cons_cfg)

    def run(self, state: GameState, executor):
        c = cfg.load()
        cons_cfg = c.get("consumables", {})

        # Auto-consume fires before manual queue
        if self._auto_consume_ready(state, c, cons_cfg):
            auto_type = cons_cfg.get("auto_consumable", "")
            state.add_log(f"Auto-consuming {auto_type}.")
            executor.execute(Action("consume", type=auto_type), state)
            return

        # Manual queue — not gated by timer limit
        try:
            consume_type = self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("consume", type=consume_type), state)
