"""
Persisted notification history — notifications.json in the writable data dir.

Each entry: {id, ts, created_at, event_type, message, status}
status is one of "unread", "read", "deleted" (soft-delete — deleted entries
stay in the file but are filtered out of load()'s default view).
"""

import json
import os
import threading
import time as _time
from datetime import datetime, timezone

import paths

NOTIFICATIONS_PATH = os.path.join(paths.data_dir(), "notifications.json")

_lock = threading.Lock()
_id_lock = threading.Lock()
_last_id = 0


def _next_id() -> str:
    """Millisecond timestamp, clamped to be strictly increasing so rapid
    back-to-back notifications (e.g. several events in one poll cycle) never
    collide — collisions would make toggle/delete-by-id affect the wrong
    entry."""
    global _last_id
    with _id_lock:
        candidate = int(_time.time() * 1000)
        if candidate <= _last_id:
            candidate = _last_id + 1
        _last_id = candidate
        return str(candidate)


def _read() -> list:
    if not os.path.exists(NOTIFICATIONS_PATH):
        return []
    try:
        with open(NOTIFICATIONS_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _write(notifs: list):
    with _lock:
        with open(NOTIFICATIONS_PATH, "w") as f:
            json.dump(notifs, f, indent=2)


def load() -> list:
    """Full history, including deleted entries (callers filter as needed)."""
    return _read()


def add(event_type: str, message: str, ts: str) -> dict:
    """Append a new unread notification and persist it. Returns the new entry."""
    entry = {
        "id": _next_id(),
        "ts": ts,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "message": message,
        "status": "unread",
    }
    notifs = _read()
    notifs.append(entry)
    _write(notifs)
    return entry


def set_status(notif_id: str, status: str) -> bool:
    """Update one entry's status. Returns True if the id was found."""
    notifs = _read()
    found = False
    for n in notifs:
        if n.get("id") == notif_id:
            n["status"] = status
            found = True
            break
    if found:
        _write(notifs)
    return found


def mark_all_read():
    notifs = _read()
    changed = False
    for n in notifs:
        if n.get("status") == "unread":
            n["status"] = "read"
            changed = True
    if changed:
        _write(notifs)
