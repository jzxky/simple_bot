"""
Action cooldown table and armed-robbery action timer guard.
"""

# Minutes each action type holds the action timer
ACTION_COOLDOWNS: dict[str, int] = {
    "community_service":      10,
    "community_service_away":  5,
    "dog_trains":              5,
    "fire_duties":            10,
    "career_training":        10,
    "university":             10,
    "drug_manufacturing":     10,
    "training_centre":        10,
}

# Energy % breakpoints → crime cycle minutes (mirrors the UI dropdown)
_ENERGY_TABLE: list[tuple[float, int]] = [
    (7.5, 10), (8.3, 11), (9.2, 12), (13.3, 13), (15.6, 14),
    (16.7, 15), (17.8, 16), (18.9, 17), (30.0, 18), (31.7, 19),
    (33.3, 20), (35.0, 21), (36.7, 22), (38.3, 23), (53.3, 24),
    (55.6, 25), (57.8, 26), (60.0, 27), (62.2, 28), (64.4, 29),
    (100.0, 30),
]


def energy_pct_to_mins(pct: float) -> float:
    """Interpolate an energy % to crime-cycle minutes using the UI dropdown table."""
    if pct <= _ENERGY_TABLE[0][0]:
        return float(_ENERGY_TABLE[0][1])
    if pct >= _ENERGY_TABLE[-1][0]:
        return float(_ENERGY_TABLE[-1][1])
    for i in range(len(_ENERGY_TABLE) - 1):
        lo_pct, lo_mins = _ENERGY_TABLE[i]
        hi_pct, hi_mins = _ENERGY_TABLE[i + 1]
        if lo_pct <= pct <= hi_pct:
            t = (pct - lo_pct) / (hi_pct - lo_pct)
            return lo_mins + t * (hi_mins - lo_mins)
    return float(_ENERGY_TABLE[-1][1])


def should_skip_action_for_armed_robbery(state, action_cooldown_mins: int) -> bool:
    """
    Return True if the action should be skipped to preserve the action timer
    for an upcoming armed robbery.

    Conditions (all must be true to block):
    - Primary aggravated crime is armed robbery
    - Occupation is not Gangster
    - action_cooldown_mins > time until energy drops to the armed robbery threshold
    """
    import config as cfg
    c = cfg.load()
    crimes_cfg = c.get("aggravated_crimes", {})
    if crimes_cfg.get("primary", {}).get("crime") != "armed":
        return False
    if "gangster" in state.occupation.lower():
        return False
    threshold = float(crimes_cfg.get("primary", {}).get("energy_threshold", 100))
    time_to_threshold = energy_pct_to_mins(threshold) - energy_pct_to_mins(state.energy)
    return action_cooldown_mins > time_to_threshold
