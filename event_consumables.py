"""
Canonical event-boss consumable definitions (collected on bossevent.asp,
consumed via /profile/consumables.asp?action=consume&type=<Name>).

Every event drops the same 8 effects under different item names, so toggles
are keyed by effect and ALIASES maps each event's item names onto them.

EFFECTS maps each effect to (label, condition kind, condition param):
  - "timer"       : consume when state.timers[param] is present and not ready
  - "earn_timer"  : like "timer", but only in manual earn mode
  - "energy"      : consume when state.energy < 100
  - "always"      : consume whenever stock remains
  - "unsupported" : never auto-consumed (toggle shown but inert)
"""

# Consume priority order (matches the original alphabetical item order)
EFFECT_ORDER = ["case", "launder", "travel", "agg_strength", "agg_pro", "earn", "action", "random"]

EFFECTS = {
    "case":         ("Case",                    "timer",       "case"),
    "launder":      ("Laundering",              "timer",       "launder"),
    "travel":       ("Travel",                  "timer",       "travel"),
    "action":       ("Action",                  "timer",       "action"),
    "agg_strength": ("Agg strength 100%",       "energy",      None),
    "agg_pro":      ("+1hr agg pro",            "always",      None),
    "earn":         ("Earn (manual mode only)", "earn_timer",  "earn"),
    "random":       ("Random prize",            "unsupported", None),
}

# Item name (as in bossevent.asp's type=) -> effect, per event
ALIASES = {
    # Summer event
    "Burger": "case", "Coffee": "launder", "Egg": "travel", "Watermelon": "action",
    "Fries": "agg_strength", "Milk": "agg_pro", "Popcorn": "earn", "Lightning": "random",
    # Halloween event
    "Ghost": "case", "Hat": "launder", "Cat": "travel", "Bat": "action",
    "Skull": "agg_strength", "Candy": "agg_pro", "Applecider": "earn", "Pumpkin": "random",
}

_ALIASES_LOWER = {k.lower(): v for k, v in ALIASES.items()}


def effect_for(name: str):
    """Effect id for an item name (case-insensitive), or None if unknown."""
    return _ALIASES_LOWER.get((name or "").lower())


def item_names(effect: str) -> list:
    """All known item names for an effect, in ALIASES order."""
    return [n for n, e in ALIASES.items() if e == effect]


def effect_toggles(consume_cfg: dict) -> dict:
    """{effect: bool} from the event_boss.consume config. Falls back to the
    legacy per-item-name keys (e.g. "Burger": true) for configs saved before
    toggles were keyed by effect."""
    consume_cfg = consume_cfg or {}
    out = {}
    for eff in EFFECT_ORDER:
        if eff in consume_cfg:
            out[eff] = bool(consume_cfg[eff])
        else:
            out[eff] = any(consume_cfg.get(n, False) for n in item_names(eff))
    return out
