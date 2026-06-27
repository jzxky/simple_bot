"""
Earn planner — lifetime caps on how many of each auto-earn the bot completes.

Maps auto-earn schedule_value identifiers to the earn-type names used in the
character-history "Earn History" tables, and reads completed counts from the
cached character history.

Only auto-earnable values (those with a schedule_value) are mappable here;
manual earns (Pizza/Bar/711) have no schedule_value and are never planned.
"""

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


def planner_view(limits: dict, active_earn: str = "", history: dict | None = None) -> dict:
    """Build the data the UI needs: availability + per-listed-earn completed counts."""
    data = history if history is not None else ch.load()
    counts = _completed_counts(data)
    earns = []
    for value, limit in (limits or {}).items():
        name = HISTORY_NAME.get(value)
        if not name:
            continue
        earns.append({
            "value": value,
            "history_name": name,
            "completed": counts.get(name, 0),
            "limit": limit,
        })
    return {
        "available": is_available(data),
        "earns": earns,
        "active": active_earn,
        "mappable": HISTORY_NAME,
    }
