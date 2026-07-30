"""
Earn planner — lifetime caps on how many of each auto-earn the bot completes.

Maps auto-earn schedule_value identifiers to the earn-type names used in the
character-history "Earn History" tables, and reads completed counts from the
cached character history.

Only auto-earnable values (those with a schedule_value) are mappable here;
manual earns (Pizza/Bar/711) have no schedule_value and are never planned.
"""

import re
import character_history as ch

# schedule_value (auto-earn identifier) → character-history "type" name
HISTORY_NAME = {
    "whore":               "Whore",
    "street_fight":        "Street Fighter",
    "joy_ride":            "Joy Ride",
    "pimp":                "Pimp",
    "shoplift":            "Shoplifting",
    "steal_cheques":       "Stealing Cheques",
    "nurse":               "Nurse",
    "doctor":              "Doctor",
    "surgeon":             "Surgeon",
    "hospital_director":   "Hospital Director",
    "mechanic":            "Mechanic",
    "technician":          "Technician",
    "engineer":            "Engineer",
    "chief_engineer":      "Chief Engineer",
    "bank_teller":         "Bank Teller",
    "mortician_assistant": "Mort Assistant",
    "legal_secretary":     "Legal Sec",
    "drag_racing":         "Drag Racing",
    "hack_bank":           "Hacking",
    "scamming":            "Scams",
}

# schedule_value → name shown in the earn-queue list (.mm-earn-queue-row-name).
# These differ from both schedule_value and the history names (e.g. queue shows
# "Scamming" while history shows "Scams"). Confirmed: scamming → "Scamming".
# The rest are best-effort; matching also falls back to the history name, and
# comparison is whitespace/case-insensitive, so minor differences still match.
QUEUE_NAME = {
    "whore":               "Whore",
    "street_fight":        "Streetfight",
    "joy_ride":            "Joyride",
    "pimp":                "Pimp",
    "shoplift":            "Shoplift",
    "steal_cheques":       "Steal Cheques",
    "nurse":               "Nurse at local hospital",
    "doctor":              "Doctor at local hospital",
    "surgeon":             "Surgeon at local hospital",
    "hospital_director":   "Hospital Director",
    "mechanic":            "Mechanic at local vehicle yard",
    "technician":          "Technician at local vehicle yard",
    "engineer":            "Engineer at local Construction Site",
    "chief_engineer":      "Chief Engineer at local Construction Company",
    "bank_teller":         "Work at local bank",
    "mortician_assistant": "Mortician Assistant",
    "legal_secretary":     "Legal Secretary",
    "drag_racing":         "Drag racing",
    "hack_bank":           "Hack bank account",
    "scamming":            "Scamming",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "").lower()


def matches_queue_name(schedule_value: str, row_name: str) -> bool:
    """True if a queue-row name belongs to the given auto-earn. Compares against
    the queue-name mapping and the history-name mapping, whitespace/case-insensitive."""
    target = _norm(row_name)
    if not target:
        return False
    candidates = {_norm(QUEUE_NAME.get(schedule_value, "")),
                  _norm(HISTORY_NAME.get(schedule_value, ""))}
    candidates.discard("")
    return target in candidates


def queued_remaining(schedule_value: str, rows) -> int:
    """Sum (total − completed) across queue rows matching this earn.

    `rows` is an iterable of (name, completed, total) tuples parsed from the
    .mm-earn-queue-row elements on earn.asp."""
    total = 0
    for name, completed, tot in rows:
        if matches_queue_name(schedule_value, name):
            total += max(0, tot - completed)
    return total


def is_available(history: dict | None = None) -> bool:
    """True if the cached character history has a non-empty Earn History,
    which proves the character has access to the in-game feature."""
    data = history if history is not None else ch.load()
    return bool(data.get("earn_history"))


def _completed_counts(history: dict | None = None) -> dict:
    """Return {history_type_name: count} flattened across all earn-history categories."""
    data = history if history is not None else ch.load()
    counts = {}
    for cat in data.get("earn_history", []):
        for entry in cat.get("entries", []):
            name = entry.get("type", "")
            if name:
                counts[name] = entry.get("count", 0)
    return counts


def completed_count(schedule_value: str, history: dict | None = None) -> int:
    """Lifetime completed count for an auto-earn, via the history-name mapping.
    Returns 0 if the earn is unmapped or absent from history."""
    name = HISTORY_NAME.get(schedule_value)
    if not name:
        return 0
    return _completed_counts(history).get(name, 0)


def _catalog_labels() -> dict:
    """Return {schedule_value: label} from the earn catalog JSON."""
    import os, json, paths
    path = os.path.join(paths.data_dir(), "available_earns.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
    except Exception:
        return {}
    return {e["schedule_value"]: e["label"] for e in entries if e.get("schedule_value")}


def planner_view(limits: dict, active_earn: str = "", history: dict | None = None) -> dict:
    """Build the data the UI needs: availability + per-listed-earn completed counts."""
    data = history if history is not None else ch.load()
    counts = _completed_counts(data)
    catalog = _catalog_labels()
    mappable = {v: catalog.get(v, name) for v, name in HISTORY_NAME.items()}
    earns = []
    for value, limit in (limits or {}).items():
        history_name = HISTORY_NAME.get(value)
        if not history_name:
            continue
        earns.append({
            "value": value,
            "history_name": history_name,
            "completed": counts.get(history_name, 0),
            "limit": limit,
        })
    return {
        "available": is_available(data),
        "earns": earns,
        "active": active_earn,
        "mappable": mappable,
    }
