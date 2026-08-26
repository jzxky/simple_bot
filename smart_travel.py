"""
Smart Travel director.

Decides which city the bot should be in based on a user-configurable priority
list of travel reasons. Each reason maps to a city and an "active" check.

City map:
    Chicago  — Bionics store (window) + Gym (transient)
    Auckland — Weapon store (window)
    Beirut   — Casino (transient)
    <home>   — fallback when nothing is pending

This module is pure decision logic: `decide_target_city()` returns a
plan dict. Wiring it into travel is done separately.
"""

CHICAGO = "Chicago"
AUCKLAND = "Auckland"
BEIRUT = "Beirut"

GYM_COOLDOWN_SECS = 12 * 3600
TWO_HOURS = 2 * 3600

DEFAULT_PRIORITY = [
    "bionics_window",
    "weapon_window",
    "lawyer_cases",
    "gym",
    "casino",
]


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
    return max(0.0, (last_gym_use + GYM_COOLDOWN_SECS) - now_ts)


def _secs_until_casino(now_ts: float, release_at: float) -> float:
    return max(0.0, release_at - now_ts)


def _check_bionics_window(ctx: dict) -> "tuple[str, str] | None":
    bionics = ctx.get("bionics", {})
    if bionics.get("enabled", False) and window_active(bionics, ctx.get("ingame_mins")):
        return CHICAGO, "bionics store window"
    return None


def _check_weapon_window(ctx: dict) -> "tuple[str, str] | None":
    weapon = ctx.get("weapon", {})
    if weapon.get("enabled", False) and window_active(weapon, ctx.get("ingame_mins")):
        return AUCKLAND, "weapon store window"
    return None


def _check_lawyer_cases(ctx: dict) -> "tuple[str, str] | None":
    if not ctx.get("law_auto_travel", False):
        return None
    cases_by_city = ctx.get("lawyer_cases_by_city", {})
    if not cases_by_city:
        return None
    current = (ctx.get("current_city", "") or "").lower()
    if any(city.lower() == current and cases for city, cases in cases_by_city.items()):
        return None  # stay — cases in current city
    best_city = max(cases_by_city, key=lambda c: cases_by_city[c])
    if cases_by_city[best_city]:
        return best_city, f"lawyer cases pending in {best_city}"
    return None


def _check_gym(ctx: dict) -> "tuple[str, str] | None":
    gym = ctx.get("gym", {})
    if (gym.get("enabled", False) and gym.get("auto_travel", False)
            and _secs_until_gym(ctx["now_ts"], ctx.get("last_gym_use", 0.0)) <= 0):
        return CHICAGO, "gym due"
    return None


def _check_casino(ctx: dict) -> "tuple[str, str] | None":
    casino = ctx.get("casino", {})
    if (casino.get("enabled", False) and casino.get("auto_travel", False)
            and _secs_until_casino(ctx["now_ts"], ctx.get("casino_release_at", 0.0)) <= 0):
        return BEIRUT, "casino due"
    return None


REASON_CHECKERS = {
    "bionics_window": _check_bionics_window,
    "weapon_window": _check_weapon_window,
    "lawyer_cases": _check_lawyer_cases,
    "gym": _check_gym,
    "casino": _check_casino,
}


def decide_target_city(ctx: dict) -> dict:
    """Return a travel plan given a context dict.

    ctx keys:
        now_ts             : float unix seconds (for cooldown maths)
        ingame_mins        : int | None
        current_city       : str
        home_city          : str (the character's actual home city)
        smart              : smart_travel config dict
        bionics            : bionics config dict
        weapon             : weapon_store config dict
        gym                : gym config dict
        casino             : casino config dict
        last_gym_use       : float
        casino_release_at  : float
        lawyer_cases_by_city : dict
        law_auto_travel    : bool

    Returns: {"target": <city or None>, "stay": bool, "reason": str}
    """
    current = ctx.get("current_city", "") or ""
    smart = ctx.get("smart", {})

    home_sel = smart.get("home", "home_city")
    home = ctx.get("home_city", "") if home_sel == "home_city" else home_sel

    priority = smart.get("priority_order", DEFAULT_PRIORITY)
    if not priority:
        priority = DEFAULT_PRIORITY

    for reason_key in priority:
        checker = REASON_CHECKERS.get(reason_key)
        if not checker:
            continue
        result = checker(ctx)
        if result:
            target_city, reason = result
            return _plan(target_city, current, reason)

    # Chain: if in a transient city (not home), check if another task is due
    # within 2h — go there instead of bouncing home.
    now_ts = ctx["now_ts"]
    gym = ctx.get("gym", {})
    casino = ctx.get("casino", {})
    if current in (CHICAGO, BEIRUT) and current.lower() != (home or "").lower():
        best_city, best_secs = None, None
        if gym.get("enabled", False) and gym.get("auto_travel", False) and current != CHICAGO:
            s = _secs_until_gym(now_ts, ctx.get("last_gym_use", 0.0))
            best_city, best_secs = CHICAGO, s
        if casino.get("enabled", False) and casino.get("auto_travel", False) and current != BEIRUT:
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
