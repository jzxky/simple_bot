"""
Canonical event-boss consumable definitions (collected on bossevent.asp,
consumed via /profile/consumables.asp?action=consume&type=<Name>).

INFO maps each item to (effect label, condition kind, condition param):
  - "timer"       : consume when state.timers[param] is present and not ready
  - "energy"      : consume when state.energy < 100
  - "always"      : consume whenever stock remains
  - "unsupported" : never auto-consumed (toggle shown but inert)
"""

# Order as displayed on bossevent.asp
EVENT_ORDER = ["Burger", "Coffee", "Egg", "Fries", "Lightning", "Milk", "Popcorn", "Watermelon"]

INFO = {
    "Burger":     ("Resets Case timer",       "timer",       "case"),
    "Coffee":     ("Resets Laundering timer",  "timer",       "launder"),
    "Egg":        ("Resets Travel timer",      "timer",       "travel"),
    "Fries":      ("Restores agg strength",    "energy",      None),
    "Lightning":  ("Random prize",             "unsupported", None),
    "Milk":       ("+1h Agg pro",              "always",      None),
    "Popcorn":    ("Resets Earn timer",        "unsupported", None),
    "Watermelon": ("Resets Action timer",      "timer",       "action"),
}

# Items the consume task actually acts on.
SUPPORTED = [n for n in EVENT_ORDER if INFO[n][1] != "unsupported"]
