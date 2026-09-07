"""
Drug middling task — triggered by !middle commands received via in-game comms,
or manually via the UI.
"""

import queue
import re

from tasks.base import Task, Action
from state import GameState

MIDDLING_RANKS = {"Piciotto", "Enforcer", "Dealer", "Giovane D'Honore"}
_HOME_CITY_REQUIRED_RANKS = {"Enforcer", "Dealer", "Giovane D'Honore"}

_middling_queue: "queue.Queue | None" = None


def set_middling_queue(q: "queue.Queue"):
    global _middling_queue
    _middling_queue = q


def parse_middle_command(text: str):
    """Parse a !middle command from message text.
    Returns (runner, buyer) or None.
    Only the first line is checked."""
    first_line = text.split("\n", 1)[0].strip()
    m = re.match(r"^!middle\s+(\S+)\s+(\S+)", first_line, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    return None


def validate_middle_players(runner: str, buyer: str) -> "str | None":
    """Check both runner and buyer are active (alive) players.
    Case-insensitive lookup. Returns an error string or None on success."""
    import player_db
    all_players = player_db.get_all_players()
    active_lower = {p["username"].lower(): p["username"] for p in all_players if p.get("active")}
    missing = []
    if runner.lower() not in active_lower:
        missing.append(runner)
    if buyer.lower() not in active_lower:
        missing.append(buyer)
    if missing:
        return f"player(s) not found in active list: {', '.join(missing)}"
    return None


class MiddlingTask(Task):
    priority = 90
    label = "Drug Middling"

    def __init__(self, middling_queue: queue.Queue):
        self._queue = middling_queue

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        if state.rank not in MIDDLING_RANKS:
            return False
        if state.rank in _HOME_CITY_REQUIRED_RANKS and not state.in_home_city():
            return False
        import config as cfg
        if not cfg.load().get("middling", {}).get("enabled", False):
            return False
        return not self._queue.empty()

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        if state.rank not in MIDDLING_RANKS:
            reasons.append(f"Rank '{state.rank}' cannot middle")
        if state.rank in _HOME_CITY_REQUIRED_RANKS and not state.in_home_city():
            reasons.append("Not in home city")
        import config as cfg
        if not cfg.load().get("middling", {}).get("enabled", False):
            reasons.append("Middling disabled")
        if self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        try:
            item = self._queue.get_nowait()
        except Exception:
            return
        action_kind = item.get("action", "do_middling")
        executor.execute(Action(action_kind, **item), state)
