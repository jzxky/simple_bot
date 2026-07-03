"""
Smart Travel director.

Decides which city the bot should be in, given the gym/casino cooldowns and the
bionics/weapon store windows, to minimise time in the gym/casino cities and
maximise full-window coverage of the store cities.

City map:
    Chicago  — Bionics store (window) + Gym (transient)
    Auckland — Weapon store (window)
    Beirut   — Casino (transient)
    <home>   — fallback when nothing is pending

This module is pure decision logic (Phase 1): `decide_target_city()` returns a
plan dict. Wiring it into travel is done separately.
"""

from datetime import datetime, time as _dtime

CHICAGO = "Chicago"
AUCKLAND = "Auckland"
BEIRUT = "Beirut"

GYM_COOLDOWN_SECS = 12 * 3600
TWO_HOURS = 2 * 3600


def _parse_hhmm(s: str) -> "_dtime | None":
    try:
        h, m = str(s).split(":")
        return _dtime(int(h), int(m))
    except Exception:
        return None


def _window_active(cfg_store: dict, now: datetime) -> bool:
    """True if the store has a time window enabled and `now` falls within it.
    Handles windows that wrap past midnight (start > end)."""
    if not cfg_store.get("use_time_window", False):
        return False
    start = _parse_hhmm(cfg_store.get("window_start", "00:00"))
    end = _parse_hhmm(cfg_store.get("window_end", "23:59"))
    if start is None or end is None:
        return False
    t = now.time()
    if start <= end:
        return start <= t <= end
    return t >= start or t <= end   # wraps midnight


def _secs_until_gym(now_ts: float, last_gym_use: float) -> float:
    """Seconds until the gym is next due (0 if due now)."""
    return max(0.0, (last_gym_use + GYM_COOLDOWN_SECS) - now_ts)


def _secs_until_casino(now_ts: float, release_at: float) -> float:
    """Seconds until the casino is next playable (0 if available now)."""
    return max(0.0, release_at - now_ts)


def decide_target_city(ctx: dict) -> dict:
    """Return a travel plan given a context dict.

    ctx keys:
        now            : datetime (server/local time for window comparison)
        now_ts         : float unix seconds (for cooldown maths)
        current_city   : str
        home_city      : str (the character's actual home city)
        smart          : smart_travel config dict
        bionics        : bionics config dict
        weapon         : weapon_store config dict
        gym            : gym config dict
        casino         : casino config dict
        last_gym_use   : float
        casino_release_at : float

    Returns: {"target": <city or None>, "stay": bool, "reason": str}
        target == current_city / None with stay=True  → remain here.
    """
    now = ctx["now"]
    now_ts = ctx["now_ts"]
    current = ctx.get("current_city", "") or ""
    smart = ctx.get("smart", {})
    bionics = ctx.get("bionics", {})
    weapon = ctx.get("weapon", {})
    gym = ctx.get("gym", {})
    casino = ctx.get("casino", {})

    store_priority = smart.get("store_priority", "bionics")
    window_mode = smart.get("window_vs_activity", "windows")

    # --- Resolve the home target ---
    home_sel = smart.get("home", "home_city")
    home = ctx.get("home_city", "") if home_sel == "home_city" else home_sel

    # --- Active store windows (ignore a store entirely until it has a window) ---
    bionics_win = bionics.get("enabled", False) and _window_active(bionics, now)
    weapon_win = weapon.get("enabled", False) and _window_active(weapon, now)

    # Overlapping windows in different cities → keep the priority winner.
    if bionics_win and weapon_win:
        if store_priority == "weapon":
            bionics_win = False
        else:
            weapon_win = False

    window_city = CHICAGO if bionics_win else (AUCKLAND if weapon_win else None)

    # --- Transient tasks due? ---
    gym_due = (gym.get("enabled", False) and gym.get("auto_travel", False)
               and _secs_until_gym(now_ts, ctx.get("last_gym_use", 0.0)) <= 0)
    casino_due = (casino.get("enabled", False) and casino.get("auto_travel", False)
                  and _secs_until_casino(now_ts, ctx.get("casino_release_at", 0.0)) <= 0)

    # --- A window is active ---
    if window_city:
        if window_mode == "windows":
            # Windows are sacrosanct: stay in the window city for the whole window.
            return _plan(window_city, current, f"honouring {window_city} store window")
        # window_mode == "activity": leave for a due transient in another city, else stay.
        if gym_due and window_city != CHICAGO:
            return _plan(CHICAGO, current, "gym due (activity priority over window)")
        if casino_due and window_city != BEIRUT:
            return _plan(BEIRUT, current, "casino due (activity priority over window)")
        return _plan(window_city, current, f"honouring {window_city} store window")

    # --- No window active: service due transient tasks, else home ---
    if gym_due:
        return _plan(CHICAGO, current, "gym due")
    if casino_due:
        return _plan(BEIRUT, current, "casino due")

    return _plan(home, current, "nothing pending — heading home")


def _plan(target: str, current: str, reason: str) -> dict:
    if not target or target.lower() == (current or "").lower():
        return {"target": None, "stay": True, "reason": reason}
    return {"target": target, "stay": False, "reason": reason}
