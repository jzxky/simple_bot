"""
Shared time-window / check-interval helpers for the bionics and weapon-store
tasks.

Interval selection rule (confirmed):
  * window interval    — when `use_time_window` is ON *and* the in-game time is
                         inside the configured window.
  * no-window interval — in every other case (toggle OFF, or toggle ON but the
                         in-game time is currently outside the window).

Legacy `check_interval_minutes` is honoured as a fallback when the new
per-mode keys are absent.
"""


def hhmm_to_mins(s):
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def in_window(store: dict, ingame_mins) -> bool:
    """True if the store's window is set and `ingame_mins` (minute-of-day) is
    inside it. Handles windows that wrap past midnight. False when the in-game
    time is unknown."""
    if ingame_mins is None:
        return False
    start = hhmm_to_mins(store.get("window_start", "00:00"))
    end = hhmm_to_mins(store.get("window_end", "23:59"))
    if start is None or end is None:
        return False
    if start < end:
        return start < ingame_mins < end
    return ingame_mins > start or ingame_mins < end   # wraps midnight


def window_sig(store: dict) -> str:
    """Signature identifying the current window's times (used to tell a genuine
    expiry from a restock that moved the window)."""
    return f"{store.get('window_start', '')}-{store.get('window_end', '')}"


def _minutes(store: dict, key: str, legacy_default: int) -> int:
    val = store.get(key, store.get("check_interval_minutes", legacy_default))
    try:
        return max(1, int(val))
    except (TypeError, ValueError):
        return legacy_default


def interval_secs(store: dict, ingame_mins) -> int:
    """Seconds between checks, selected per the window rule above."""
    win_min   = _minutes(store, "check_interval_window_minutes", 5)
    nowin_min = _minutes(store, "check_interval_no_window_minutes", 16)
    if store.get("use_time_window", False) and in_window(store, ingame_mins):
        return win_min * 60
    return nowin_min * 60
