"""
In-process revision counter for user-facing settings changes.

Bumped on every /save and whenever the bot itself auto-changes a user-facing
setting (e.g. auto-disabling a store buy window, or setting a restock window).
Open browser tabs read it via /status to know when their settings form has gone
stale and should re-sync.

In-memory only (resets on restart, which is fine — tabs reconnect/reload then).
"""

_rev = 0


def bump():
    global _rev
    _rev += 1


def get() -> int:
    return _rev
