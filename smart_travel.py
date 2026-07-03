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

CHICAGO = "Chicago"
AUCKLAND = "Auckland"
BEIRUT = "Beirut"

GYM_COOLDOWN_SECS = 12 * 3600
TWO_HOURS = 2 * 3600


def _hhmm_to_mins(s: str) -> "int | None":
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def window_active(cfg_store: dict, ingame_mins) -> bool:
    """True if the store has a time window enabled and `ingame_mins` (in-game
    minute-of-day) falls within it. Handles windows that wrap past midnight.
    Matches the bionics/weapon task window logic."""
    if not cfg_store.get("use_time_window", False) or ingame_mins is None:
        return False
    start = _hhmm_to_mins(cfg_store.get("window_start", "00:00"))
    end = _hhmm_to_mins(cfg_store.get("window_end", "23:59"))
    if start is None or end is None:
        return False
    if start < end:
        return start < ingame_mins < end
    return ingame_mins > start or ingame_mins < end   # wraps midnight


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
    ingame_mins = ctx.get("ingame_mins")
    bionics_win = bionics.get("enabled", False) and window_active(bionics, ingame_mins)
    weapon_win = weapon.get("enabled", False) and window_active(weapon, ingame_mins)

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

    # --- No window active: service due transient tasks, else chain/home ---
    if gym_due:
        return _plan(CHICAGO, current, "gym due")
    if casino_due:
        return _plan(BEIRUT, current, "casino due")

    # Option-B chain-then-home: if we're sitting in a transient city (just finished
    # a gym/casino run) and another transient is due within 2h in a different city,
    # go there next rather than bouncing home; otherwise head home.
    if current in (CHICAGO, BEIRUT) and current.lower() != (home or "").lower():
        best_city, best_secs = None, None
        if (gym.get("enabled", False) and gym.get("auto_travel", False) and current != CHICAGO):
            s = _secs_until_gym(now_ts, ctx.get("last_gym_use", 0.0))
            best_city, best_secs = CHICAGO, s
        if (casino.get("enabled", False) and casino.get("auto_travel", False) and current != BEIRUT):
            s = _secs_until_casino(now_ts, ctx.get("casino_release_at", 0.0))
            if best_secs is None or s < best_secs:
                best_city, best_secs = BEIRUT, s
        if best_city is not None and best_secs is not None and best_secs <= TWO_HOURS:
            return _plan(best_city, current, f"next transient ({best_city}) due within 2h — chaining")

    return _plan(home, current, "nothing pending — heading home")


def _plan(target: str, current: str, reason: str) -> dict:
    if not target or target.lower() == (current or "").lower():
        return {"target": None, "stay": True, "reason": reason}
    return {"target": target, "stay": False, "reason": reason}
