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


def _ecstasy_blocked_by_fails(state: GameState) -> bool:
    return state.agg_fail_count() >= 3


def _ecstasy_target_threshold(state: GameState, agg_cfg: dict) -> float:
    """Energy % that ecstasy should fill up to.

    - Selected (primary) crime is not hack → primary threshold (hack is the only
      crime with a distinct away variant, so non-hack uses primary everywhere).
    - Selected crime is hack:
        • away from home → away (secondary) crime threshold
        • in home city   → primary threshold
    """
    primary_crime = agg_cfg.get("primary", {}).get("crime", "")
    if primary_crime == "hack" and not state.in_home_city():
        return float(agg_cfg.get("away_crime", {}).get("energy_threshold", 50))
    return float(agg_cfg.get("primary", {}).get("energy_threshold", 50))


def _passes_timer_gate(consume_type: str, state: GameState, cfg_cons: dict) -> bool:
    """Return True if the consumable's timer condition allows consuming."""
    limit_secs = _timer_limit_secs(cfg_cons)
    if limit_secs == 0:
        return True

    if consume_type == "ecstasy":
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

    now = state._estimated_server_time()
    if now is None:
        return False
    remaining_secs = max(0, int((end - now).total_seconds()))
    return remaining_secs > limit_secs


def _smart_count(consume_type: str, state: GameState, cfg_cons: dict, agg_cfg: dict, respect_buffer: bool = True) -> int:
    """Return how many units to consume in one batch (floor(available_mins / 3)), capped by stock and headroom."""
    limit = int(cfg_cons.get("consumable_limit", 33))
    buffer_ = int(cfg_cons.get("buffer", 0)) if respect_buffer else 0
    headroom = max(0, (limit - buffer_) - (state.consumables_24h or 0))
    stock = state.consumables.get(consume_type, 0)
    cap = min(headroom, stock)
    if cap <= 0:
        return 0

    if consume_type == "ecstasy":
        if _ecstasy_blocked_by_fails(state):
            return 0
        threshold_pct = _ecstasy_target_threshold(state, agg_cfg)
        current_pct = state.energy if state.energy is not None else 0.0
        gap_mins = _energy_to_mins(threshold_pct) - _energy_to_mins(current_pct)
        count = math.ceil(gap_mins / 3)
    else:
        timer_key = CONSUMABLE_TIMER_MAP.get(consume_type)
        if timer_key is None:
            return 1
        timer = state.timers.get(timer_key, {})
        if timer.get("ready", True):
            return 0
        end = timer.get("end")
        if end is None:
            return 0
        now = state._estimated_server_time()
        if now is None:
            return 0
        remaining_secs = max(0, int((end - now).total_seconds()))
        count = math.floor(remaining_secs / 180)

    return min(max(0, count), cap)


def _ecstasy_passes_gate(state: GameState, cfg_cons: dict, agg_cfg: dict) -> bool:
    """Ecstasy gate: gap between current and threshold energy > floor(timer_limit_mins)."""
    if _ecstasy_blocked_by_fails(state):
        return False
    limit_secs = _timer_limit_secs(cfg_cons)
    if limit_secs == 0:
        return True

    limit_mins = math.floor(limit_secs / 60)

    threshold_pct = _ecstasy_target_threshold(state, agg_cfg)

    current_pct = state.energy if state.energy is not None else 0.0
    gap = _energy_to_mins(threshold_pct) - _energy_to_mins(current_pct)
    return gap > limit_mins


class ConsumeTask(Task):
    priority = 30
    label = 'Consume'

    def __init__(self, consume_queue: queue.Queue):
        self._queue = consume_queue

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        c = cfg.load()
        cons_cfg = c.get("consumables", {})
        away = state.current_city != state.home_city
        # Auto-consume has its own readiness check
        if self._auto_consume_ready(state, c, cons_cfg):
            if away and cons_cfg.get("auto_consumable", "") != "ecstasy":
                return False
            return True
        if self._queue.empty():
            return False
        if away:
            # Only ecstasy is usable outside home city
            try:
                consume_type = self._queue.queue[0]
            except IndexError:
                return False
            return consume_type == "ecstasy"
        return True

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

    def _ecstasy_bootstrap(self, state: GameState, executor, cons_cfg: dict, agg_cfg: dict, respect_buffer: bool) -> int:
        """Consume 1 ecstasy probe when energy is 0% to escape the ambiguous
        low-energy band (minutes 0/1/2 all read 0%), refresh, then compute the
        remaining count from the now-disambiguated energy reading.

        Each ecstasy restores a fixed 3 minutes of energy; _smart_count maps the
        energy% to elapsed minutes and divides the gap by 3."""
        executor.execute(Action("consume", type="ecstasy", count=1), state)
        executor.execute(Action("refresh_state"), state)
        count = _smart_count("ecstasy", state, cons_cfg, agg_cfg, respect_buffer)

        # Diagnostics — surface the limiting factor (energy gap vs daily cap vs stock)
        threshold_pct = _ecstasy_target_threshold(state, agg_cfg)
        gap_mins = _energy_to_mins(threshold_pct) - _energy_to_mins(state.energy or 0.0)
        raw = math.ceil(gap_mins / 3)
        limit = int(cons_cfg.get("consumable_limit", 33))
        buffer_ = int(cons_cfg.get("buffer", 0)) if respect_buffer else 0
        headroom = max(0, (limit - buffer_) - (state.consumables_24h or 0))
        stock = state.consumables.get("ecstasy", 0)
        state.add_log(
            f"Ecstasy probe: energy now {state.energy or 0:.1f}% (target {threshold_pct:.0f}%), "
            f"need {raw} more; headroom {headroom} (limit {limit} - buffer {buffer_} - {state.consumables_24h or 0} used/24h), "
            f"stock {stock} → consuming {count}."
        )
        return count

    def run(self, state: GameState, executor):
        c = cfg.load()
        cons_cfg = c.get("consumables", {})
        smart = cons_cfg.get("smart_consumables", False)

        # Always refresh state before any consume decision
        executor.execute(Action("refresh_state"), state)

        # Hard limit check — never consume if at or past daily cap
        limit = int(cons_cfg.get("consumable_limit", 33))
        if (state.consumables_24h or 0) >= limit:
            return

        # Auto-consume fires before manual queue
        if self._auto_consume_ready(state, c, cons_cfg):
            auto_type = cons_cfg.get("auto_consumable", "")
            count = 1
            if smart:
                agg_cfg = c.get("aggravated_crimes", {})
                if auto_type == "ecstasy" and state.energy == 0.0:
                    count = self._ecstasy_bootstrap(state, executor, cons_cfg, agg_cfg, respect_buffer=True)
                    if count > 0:
                        state.add_log(f"Auto-consuming ecstasy x{count} (post-probe).")
                        executor.execute(Action("consume", type="ecstasy", count=count), state)
                    return
                count = _smart_count(auto_type, state, cons_cfg, agg_cfg)
                if count <= 0:
                    return
            state.add_log(f"Auto-consuming {auto_type}" + (f" x{count}" if count > 1 else "") + ".")
            executor.execute(Action("consume", type=auto_type, count=count), state)
            return

        # Manual queue — not gated by timer limit
        try:
            consume_type = self._queue.get_nowait()
        except Exception:
            return
        count = 1
        if smart:
            agg_cfg = c.get("aggravated_crimes", {})
            if consume_type == "ecstasy" and state.energy == 0.0:
                count = self._ecstasy_bootstrap(state, executor, cons_cfg, agg_cfg, respect_buffer=False)
                if count > 0:
                    executor.execute(Action("consume", type="ecstasy", count=count), state)
                return
            count = _smart_count(consume_type, state, cons_cfg, agg_cfg, respect_buffer=False)
            if count <= 0:
                return
        executor.execute(Action("consume", type=consume_type, count=count), state)
