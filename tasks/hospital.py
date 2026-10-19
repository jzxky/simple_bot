"""
Hospital (City → Hospital tab): bionic implant fitting and sex changes.

The actions themselves are on-demand handlers in executor.py, triggered from the UI.
This module holds the sex-change cooldown, persisted in config. It's set from the
"Surgery Completed" journal (12 hours after the surgery, in server time), and reset
from the sex change page's "must wait 12 hours" fail message.
"""

import re
from datetime import datetime, timedelta

from state import GameState, SERVER_TIME_FMT

SEX_CHANGE_COOLDOWN = timedelta(hours=12)


def load_hospital_state() -> dict:
    import config as cfg
    return cfg.load().get("hospital_state", {})


def save_hospital_state(updates: dict):
    import config as cfg
    c = cfg.load()
    c.setdefault("hospital_state", {}).update(updates)
    cfg.save(c)


def sex_change_available_at() -> "datetime | None":
    raw = load_hospital_state().get("sex_change_available_at")
    if not raw:
        return None
    try:
        return datetime.strptime(raw, SERVER_TIME_FMT)
    except ValueError:
        return None


def sex_change_cooldown_secs(state: GameState) -> "int | None":
    """Seconds until a sex change is allowed again (0 = ready), or None when
    there's no cooldown recorded or server time isn't known yet."""
    available = sex_change_available_at()
    if available is None:
        return 0
    now = state._estimated_server_time()
    if now is None:
        return None
    return max(0, int((available - now).total_seconds()))


def record_sex_change_completed(time_str: str, state: GameState):
    """Start the 12h cooldown from a 'Surgery Completed' journal timestamp."""
    try:
        done_at = datetime.strptime(time_str.strip(), SERVER_TIME_FMT)
    except ValueError:
        state.add_log(f"Hospital: couldn't read sex change completion time '{time_str}'.")
        return
    available = done_at + SEX_CHANGE_COOLDOWN
    save_hospital_state({"sex_change_available_at": available.strftime(SERVER_TIME_FMT)})
    state.add_log(f"Hospital: sex change completed — next available at "
                  f"{available.strftime(SERVER_TIME_FMT)} (server time).")


def update_sex_change_cooldown_from_message(msg: str, state: GameState):
    """Reset the cooldown from the sex change page's fail message:
    'Your last sex change took place on 2026-10-20 08:52:06. You must wait 12 hours…'
    The time it gives matches when the cooldown ends, so it's used as-is."""
    m = re.search(r"last sex change took place on (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", msg)
    if not m:
        return
    available = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    save_hospital_state({"sex_change_available_at": available.strftime(SERVER_TIME_FMT)})
    state.add_log(f"Hospital: sex change cooldown updated — next available at "
                  f"{available.strftime(SERVER_TIME_FMT)} (server time).")
