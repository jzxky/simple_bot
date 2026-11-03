"""
Drug middling task — triggered by !middle commands received via in-game comms,
or manually via the UI.
"""

import queue
import re

from tasks.base import Task, Action
from state import GameState, norm_rank

MIDDLING_RANKS = {"piciotto", "enforcer", "dealer", "giovane d'honore"}
_HOME_CITY_REQUIRED_RANKS = {"enforcer", "dealer", "giovane d'honore"}


def drug_trade_blockers(state: GameState, rank: bool = True, home_city: bool = True) -> list:
    """Reasons the character can't run a drug-dealing action right now (empty = OK).
    rank: must be a middling rank. home_city: those ranks except Piciotto must be home."""
    reasons = []
    if not state.logged_in:
        reasons.append("Not logged in")
    if state.in_jail:
        reasons.append("In jail")
    if state.in_hospital:
        reasons.append("In hospital")
    r = norm_rank(state.rank)
    if rank and r not in MIDDLING_RANKS:
        reasons.append(f"Rank '{state.rank or 'unknown'}' can't deal drugs")
    if home_city and r in _HOME_CITY_REQUIRED_RANKS and not state.in_home_city():
        reasons.append("Not in home city")
    return reasons

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
        return not self.blocked_reasons(state)

    def blocked_reasons(self, state):
        reasons = drug_trade_blockers(state)
        import config as cfg
        if not cfg.load().get("middling", {}).get("enabled", False):
            reasons.append("Middling disabled")
        if self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        try:
            item = self._queue.get_nowait()
        except queue.Empty:
            return
        executor.execute(Action("do_middling", runner=item["runner"], buyer=item["buyer"]), state)
