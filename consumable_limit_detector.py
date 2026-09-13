"""Auto-detect the daily consumable limit from character history and rank."""

import character_history as ch

ZERO_RANKS = {"Boss", "Don", "Godfather", "Capo di Tutti Capi"}
LIMITED_RANKS = {"Sgarrista", "Capodecima", "Caporegime"}

EXCLUDED_OCCUPATIONS = {"Gangster", "Jail", "Unemployed"}

TABLE_LIMITED = [
    (1500, 15),
    (3000, 30),
    (5000, 46),
    (7000, 61),
    (None, 77),
]

TABLE_FULL = [
    (1500, 33),
    (3000, 66),
    (5000, 99),
    (7000, 132),
    (None, 165),
]


def _total_earns_excluding_jail(history: dict) -> int:
    total = 0
    for section in history.get("earn_history", []):
        cat = section.get("category", "").lower()
        if cat in ("jail", "summary"):
            continue
        for entry in section.get("entries", []):
            total += entry.get("count", 0)
    return total


def _has_legit_career(history: dict) -> bool:
    for entry in history.get("promotion_history", []):
        occ = entry.get("occupation", "")
        if occ and occ not in EXCLUDED_OCCUPATIONS:
            return True
    return False


def _limit_from_table(total_earns: int, table: list) -> int:
    for threshold, limit in table:
        if threshold is None or total_earns < threshold:
            return limit
    return table[-1][1]


def detect(rank: str) -> dict:
    history = ch.load()
    if not history:
        return {"limit": None, "reason": "No character history available"}

    rank_clean = (rank or "").strip()

    if rank_clean in ZERO_RANKS:
        return {"limit": 0, "rank": rank_clean, "reason": "Zero rank"}

    total_earns = _total_earns_excluding_jail(history)

    if rank_clean in LIMITED_RANKS and _has_legit_career(history):
        limit = _limit_from_table(total_earns, TABLE_LIMITED)
        return {
            "limit": limit,
            "rank": rank_clean,
            "total_earns": total_earns,
            "table": "limited",
        }

    limit = _limit_from_table(total_earns, TABLE_FULL)
    return {
        "limit": limit,
        "rank": rank_clean,
        "total_earns": total_earns,
        "table": "full",
    }
