"""
Earn planner — lifetime caps on how many of each auto-earn the bot completes.

Maps auto-earn schedule_value identifiers to the earn-type names used in the
character-history "Earn History" tables, and reads completed counts from the
cached character history.

Only auto-earnable values (those with a schedule_value) are mappable here;
manual earns (Pizza/Bar/711) have no schedule_value and are never planned.

Planner mode: config earn_planner.limits is an ordered {schedule_value: limit}
queue. After each character-history update the planner checks the active earn
(planner_decision) and moves to the next available, unfinished earn
(pick_next). earn_planner.done records {value: limit} for earns whose final
batch has been handed off, so they aren't picked again at the same limit.
"""

import re
import character_history as ch

# schedule_value (auto-earn identifier) → character-history "type" name
HISTORY_NAME = {
    "whore":               "Whore",
    "street_fight":        "Street Fighter",
    "joy_ride":            "Joy Ride",
    "pimp":                "Pimp",
    "newseditor":          "Newspaper Editor",
    "shoplift":            "Shoplifting",
    "steal_cheques":       "Stealing Cheques",
    "drag_racing":         "Drag Racing",
    "hack_bank":           "Hacking",
    "scamming":            "Scams",
    "inspector":           "Inspector",
    "supervisor":          "Supervisor",
    "superintendent":      "Superintendent",
    "commis_general":      "Commis-General",
    "mechanic":            "Mechanic",
    "technician":          "Technician",
    "engineer":            "Engineer",
    "chief_engineer":      "Chief Engineer",
    "nurse":               "Nurse",
    "doctor":              "Doctor",
    "surgeon":             "Surgeon",
    "hospital_director":   "Hospital Director",
    "bank_teller":         "Bank Teller",
    "loan_officer":        "Loan Officer",
    "bank_manager":        "Bank Manager",
    "legal_secretary":     "Legal Sec",
    "lawyer":              "Lawyer",
    "judge":               "Judge",
    "supreme_court_judge": "Supreme Court Judge",
    "patrol":              "Patrol",
    "paper_work":          "Paper Work",
    "arrests":             "Arrests",
    "assign_duties":       "Assign Duties",
    "mortician_assistant": "Mort Assistant",
    "mortician":           "Mortician",
    "undertaker":          "Undertaker",
    "funeral_director":    "Funeral Director",
    "vol_fire_fighter":    "Vol. Fire Fighter",
    "fire_fighter":        "Fire Fighter",
    "fire_chief":          "Fire Chief",
    "mayor":               "Mayor",
    "laundry_work":        "Laundry Work",
    "kitchen_hand":        "Kitchen Hand",
    "workshop":            "Workshop",
    "make_shank":          "Make Shank",
    "gym_workout":         "Gym workout",
    "dig_tunnel":          "Dig Tunnel",
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
    "newseditor":          "Newspaper Editor",
    "shoplift":            "Shoplift",
    "steal_cheques":       "Steal Cheques",
    "drag_racing":         "Drag racing",
    "hack_bank":           "Hack bank account",
    "scamming":            "Scamming",
    "inspector":           "Inspector",
    "supervisor":          "Supervisor",
    "superintendent":      "Superintendent",
    "commis_general":      "Commis-General",
    "mechanic":            "Mechanic at local vehicle yard",
    "technician":          "Technician at local vehicle yard",
    "engineer":            "Engineer at local Construction Site",
    "chief_engineer":      "Chief Engineer at local Construction Company",
    "nurse":               "Nurse at local hospital",
    "doctor":              "Doctor at local hospital",
    "surgeon":             "Surgeon at local hospital",
    "hospital_director":   "Hospital Director",
    "bank_teller":         "Work at local bank",
    "loan_officer":        "Loan Officer",
    "bank_manager":        "Bank Manager",
    "legal_secretary":     "Legal Secretary",
    "lawyer":              "Lawyer",
    "judge":               "Judge",
    "supreme_court_judge": "Supreme Court Judge",
    "patrol":              "Patrol",
    "paper_work":          "Paper Work",
    "arrests":             "Arrests",
    "assign_duties":       "Assign Duties",
    "mortician_assistant": "Mortician Assistant",
    "mortician":           "Mortician",
    "undertaker":          "Undertaker",
    "funeral_director":    "Funeral Director",
    "vol_fire_fighter":    "Vol. Fire Fighter",
    "fire_fighter":        "Fire Fighter",
    "fire_chief":          "Fire Chief",
    "mayor":               "Mayor",
    "laundry_work":        "Laundry Work",
    "kitchen_hand":        "Kitchen Hand",
    "workshop":            "Workshop",
    "make_shank":          "Make Shank",
    "gym_workout":         "Gym workout",
    "dig_tunnel":          "Dig Tunnel",
}


def _count_key(name: str) -> str:
    """Canonical earn name for count lookups: lowercase, letters/digits only, with
    "volunteer" abbreviated, so the catalog label "Volunteer Firefighter" matches
    the history name "Vol. Fire Fighter"."""
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return re.sub(r"^volunteer", "vol", key)


def _queue_candidates(schedule_value: str) -> set:
    """Canonical names a queue row for this earn may show: the queue-name and
    history-name mappings plus the catalog label (covers unmapped values)."""
    candidates = {_count_key(QUEUE_NAME.get(schedule_value, "")),
                  _count_key(HISTORY_NAME.get(schedule_value, "")),
                  _count_key(_catalog_labels().get(schedule_value, ""))}
    candidates.discard("")
    return candidates


def matches_queue_name(schedule_value: str, row_name: str) -> bool:
    """True if a queue-row name belongs to the given auto-earn. Compares canonical
    names (_count_key), so case, spacing and punctuation differences still match."""
    target = _count_key(row_name)
    return bool(target) and target in _queue_candidates(schedule_value)


def queued_remaining(schedule_value: str, rows) -> int:
    """Sum (total − completed) across queue rows matching this earn.

    `rows` is an iterable of (name, completed, total) tuples parsed from the
    .mm-earn-queue-row elements on earn.asp."""
    candidates = _queue_candidates(schedule_value)
    total = 0
    for name, completed, tot in rows:
        if _count_key(name) in candidates:
            total += max(0, tot - completed)
    return total


def is_available(history: dict | None = None) -> bool:
    """True if the cached character history has a non-empty Earn History,
    which proves the character has access to the in-game feature."""
    data = history if history is not None else ch.load()
    return bool(data.get("earn_history"))


def _completed_counts(history: dict | None = None) -> dict:
    """Return {_count_key(type_name): count} flattened across all earn-history categories."""
    data = history if history is not None else ch.load()
    counts = {}
    for cat in data.get("earn_history", []):
        for entry in cat.get("entries", []):
            name = entry.get("type", "")
            if name:
                counts[_count_key(name)] = entry.get("count", 0)
    return counts


def completed_count(schedule_value: str, history: dict | None = None) -> int:
    """Lifetime completed count for an auto-earn, via the history-name mapping.
    Falls back to matching the catalog label against history if unmapped."""
    counts = _completed_counts(history)
    name = HISTORY_NAME.get(schedule_value)
    if name:
        result = counts.get(_count_key(name), 0)
        if result:
            return result
    label = _catalog_labels().get(schedule_value)
    return counts.get(_count_key(label), 0) if label else 0


def _load_catalog() -> list:
    """Return the full earn catalog list from earn_catalog.json."""
    import os, json, paths
    path = paths.earn_catalog_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _catalog_labels() -> dict:
    """Return {schedule_value: label} from the earn catalog JSON."""
    return {e["schedule_value"]: e.get("label", e["schedule_value"]) for e in _load_catalog() if e.get("schedule_value")}


def _load_queue_cache() -> dict:
    """Read earn_queue_cache.json written by executor during earn checks."""
    import os, json, paths
    path = os.path.join(paths.data_dir(), "earn_queue_cache.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# In-game earn queue capacity. In auto mode the final batch for an earn is
# queued once its count is within this many of the limit.
QUEUE_SIZE = 200


def catalog_available(schedule_value: str, catalog: list | None = None) -> bool:
    """True if the earn catalog marks this earn as currently available."""
    entries = catalog if catalog is not None else _load_catalog()
    return any(e.get("schedule_value") == schedule_value and e.get("available") is True
               for e in entries)


def is_finished(value: str, limit: int, done: dict, history: dict | None = None) -> bool:
    """An earn is finished once its history count reaches the limit, or once
    the planner has handed it off (its final batch queued) at this limit.
    Raising the limit above the hand-off limit makes it eligible again."""
    handed_off_at = (done or {}).get(value)
    if handed_off_at is not None and int(limit) <= int(handed_off_at):
        return True
    return completed_count(value, history) >= int(limit)


def pick_next(limits: dict, done: dict, history: dict | None = None,
              catalog: list | None = None, skip: tuple = ()) -> "str | None":
    """First earn in planner order that is available in the catalog and not
    finished — or None if there isn't one."""
    data = history if history is not None else ch.load()
    entries = catalog if catalog is not None else _load_catalog()
    for value, limit in (limits or {}).items():
        if value in skip:
            continue
        if not catalog_available(value, entries):
            continue
        if is_finished(value, limit, done, data):
            continue
        return value
    return None


def planner_decision(mode: str, active: str, limits: dict, done: dict,
                     history: dict | None = None) -> dict:
    """What the planner should do for the active earn right now:
    {"action": "none" | "final_batch" | "advance", "count", "limit", "remaining"}.
      auto:   count >= limit - QUEUE_SIZE  → final_batch (queue limit - count, then advance)
      manual: count >= limit               → advance
    An active earn that isn't in the planner (or is already finished) → advance."""
    if active not in (limits or {}):
        return {"action": "advance", "count": 0, "limit": 0, "remaining": 0}
    limit = int(limits[active])
    count = completed_count(active, history)
    out = {"count": count, "limit": limit, "remaining": max(0, limit - count)}
    handed_off_at = (done or {}).get(active)
    if handed_off_at is not None and limit <= int(handed_off_at):
        return {**out, "action": "advance"}
    if mode == "manual":
        return {**out, "action": "advance" if count >= limit else "none"}
    return {**out, "action": "final_batch" if count >= limit - QUEUE_SIZE else "none"}


def planner_view(limits: dict, active_earn: str = "", history: dict | None = None,
                 done: dict | None = None, waiting: bool = False) -> dict:
    """Build the data the UI needs: availability + per-listed-earn completed counts."""
    data = history if history is not None else ch.load()
    counts = _completed_counts(data)
    catalog_entries = _load_catalog()
    catalog_labels = {e["schedule_value"]: e["label"] for e in catalog_entries if e.get("schedule_value")}
    catalog_by_cat = {}
    for e in catalog_entries:
        sv = e.get("schedule_value")
        if not sv:
            continue
        cat = e.get("category") or "Uncategorized"
        catalog_by_cat.setdefault(cat, []).append({"value": sv, "label": e.get("label", sv)})

    earns = []
    for value, limit in (limits or {}).items():
        history_name = HISTORY_NAME.get(value)
        label = catalog_labels.get(value, history_name or value)
        completed = 0
        if history_name:
            completed = counts.get(_count_key(history_name), 0)
        if not completed and label:
            completed = counts.get(_count_key(label), 0)
        # Handed off with its final batch queued but not all worked yet: the
        # rest is still in the game queue. Derived from history (refreshed far
        # more often than the queue snapshot), so it shrinks as earns finish.
        handed_off_at = (done or {}).get(value)
        queued = 0
        if handed_off_at is not None and int(limit) <= int(handed_off_at) and completed < int(limit):
            queued = int(handed_off_at) - completed
        earns.append({
            "value": value,
            "label": label,
            "completed": completed,
            "limit": limit,
            "queued": queued,
            "catalog_available": catalog_available(value, catalog_entries),
            "finished": is_finished(value, limit, done, data),
        })
    return {
        "available": is_available(data),
        "earns": earns,
        "active": active_earn,
        "catalog": catalog_by_cat,
        "waiting": waiting,
    }
