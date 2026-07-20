"""
War Mode — WS (whacks-survived) monitoring store.

Persists opps/friendlies watch lists and a war-events log to
data_dir/war_mode.json. Whack windows and status are computed on read:

  Window Open  = last_whack_time + (3h40m Normal | 3h Bodyguard)
  Window Close = Window Open + (40m Normal | 0m Bodyguard)
  Status: no whack time → Open; now < open → Protected;
          open ≤ now ≤ close → In-Window; now > close → Open
"""

import os
import json
import threading
from datetime import datetime, timedelta

import paths
import player_db as _db

_PATH = os.path.join(paths.data_dir(), "war_mode.json")
_lock = threading.Lock()

SIDES = ("opps", "friendlies")
WHACK_TYPES = ("Normal", "Bodyguard")
_OPEN_OFFSET = {"Normal": 3 * 60 + 40, "Bodyguard": 3 * 60}  # whack → window open (minutes)
_WINDOW_LEN  = {"Normal": 40, "Bodyguard": 0}                # open → close (minutes)
_TS_FMT = "%Y-%m-%d %H:%M:%S"
_MAX_EVENTS = 200


def _now() -> datetime:
    return datetime.now()


def _load() -> dict:
    d = {}
    if os.path.exists(_PATH):
        try:
            with open(_PATH, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
    d.setdefault("opps", [])
    d.setdefault("friendlies", [])
    d.setdefault("events", [])
    return d


def _save(d: dict):
    tmp = _PATH + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _PATH)


def _parse_ts(s):
    if not s:
        return None
    for fmt in (_TS_FMT, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _find(d, side, name):
    for e in d.get(side, []):
        if e["name"].lower() == (name or "").lower():
            return e
    return None


def _new_entry(name):
    return {"name": name, "ws": None, "whack_type": "Normal", "last_whack_time": None}


def name_exists(name) -> bool:
    lower = {u.lower() for u in _db.get_usernames()}
    return (name or "").lower() in lower


def add_name(name, side) -> "tuple[bool, str]":
    name = (name or "").strip()
    if side not in SIDES:
        return False, "Invalid list."
    if not name:
        return False, "Name required."
    if not name_exists(name):
        return False, f"'{name}' is not in the player database."
    with _lock:
        d = _load()
        if _find(d, "opps", name) or _find(d, "friendlies", name):
            return False, f"'{name}' is already tracked."
        d[side].append(_new_entry(name))
        _save(d)
    return True, f"Added {name} to {side}."


def remove_name(name, side):
    with _lock:
        d = _load()
        d[side] = [e for e in d.get(side, []) if e["name"].lower() != (name or "").lower()]
        _save(d)


def set_whack_type(name, side, whack_type):
    if whack_type not in WHACK_TYPES:
        return
    with _lock:
        d = _load()
        e = _find(d, side, name)
        if e:
            e["whack_type"] = whack_type
            _save(d)


def set_whack_time(name, side, ts_str):
    dt = _parse_ts(ts_str)
    with _lock:
        d = _load()
        e = _find(d, side, name)
        if e:
            e["last_whack_time"] = dt.strftime(_TS_FMT) if dt else None
            _save(d)


def record_ws(name, side, ws) -> bool:
    """Set a name's WS; if it increased over the stored value, stamp
    last_whack_time=now and log a war event. Returns True on such an increase."""
    with _lock:
        d = _load()
        e = _find(d, side, name)
        if e is None:
            return False
        prev = e.get("ws")
        whacked = prev is not None and ws > prev
        e["ws"] = ws
        if whacked:
            e["last_whack_time"] = _now().strftime(_TS_FMT)
            _add_event(d, f"{name} has been whacked (whacks survived {prev} → {ws}).")
        _save(d)
    return whacked


def _add_event(d, message):
    d.setdefault("events", []).insert(0, {"ts": _now().strftime(_TS_FMT), "message": message})
    d["events"] = d["events"][:_MAX_EVENTS]


def add_event(message):
    with _lock:
        d = _load()
        _add_event(d, message)
        _save(d)


def clear_events():
    with _lock:
        d = _load()
        d["events"] = []
        _save(d)


def all_names() -> list:
    """[(side, name), …] for the monitor sweep."""
    d = _load()
    return [(s, e["name"]) for s in SIDES for e in d.get(s, [])]


def _computed(e) -> dict:
    wt = e.get("whack_type", "Normal")
    lwt = _parse_ts(e.get("last_whack_time"))
    open_dt = close_dt = None
    status = "Open"
    if lwt:
        open_dt = lwt + timedelta(minutes=_OPEN_OFFSET.get(wt, 220))
        close_dt = open_dt + timedelta(minutes=_WINDOW_LEN.get(wt, 40))
        now = _now()
        if now < open_dt:
            status = "Protected"
        elif now <= close_dt:
            status = "In-Window"
        else:
            status = "Open"
    return {
        "name": e["name"],
        "ws": e.get("ws"),
        "whack_type": wt,
        "last_whack_time": e.get("last_whack_time"),
        "window_open": open_dt.strftime(_TS_FMT) if open_dt else None,
        "window_close": close_dt.strftime(_TS_FMT) if close_dt else None,
        "status": status,
    }


def get_state() -> dict:
    d = _load()
    return {
        "opps":       [_computed(e) for e in d.get("opps", [])],
        "friendlies": [_computed(e) for e in d.get("friendlies", [])],
        "events":     d.get("events", []),
    }
