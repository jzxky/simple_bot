import json
import os
import threading
import paths

CONFIG_PATH = os.path.join(paths.data_dir(), "config.json")
ENV_PATH = os.path.join(paths.data_dir(), ".env")

DEFAULT_CONFIG = {
    "earns": {
        "enabled": True,
        "earn_type": "surgeon",
        "earn_mode": "auto",
        "check_interval_minutes": 30
    },
    "earn_planner": {
        "limits": {}
    },
    "aggravated_crimes": {
        "enabled": True,
        "primary": {
            "crime": "hack",
            "energy_threshold": 60
        },
        "away_crime": {
            "crime": "pickpocket",
            "energy_threshold": 50
        },
        "armed": {
            "agg_private": False,
            "agg_drug_house": False,
            "payback_private": False,
            "payback_public": False
        },
        "torch": {
            "torch_private": False,
            "torch_payback_public": "everyone",
            "torch_payback_private": "everyone"
        },
        "fallback_to_away": False
    },
    "action": {
        "enabled": True,
        "type": "community_service",
        "sub_option": "",
        "fallback_action": "",
        "career_training_stop_at_14": False
    },
    "away_action": {
        "enabled": False,
        "type": "drug_manufacturing"
    },
    "laundering": {
        "enabled": False,
        "launder_amount": 0,
        "preferred_contacts": []
    },
    "university": {
        "completed": []
    },
    "payback_mode": "everyone",
    "career_training": {
        "career": "fire"
    },
    "misc": {
        "logout_on_stop": True,
        "relog_on_session_expire": True,
        "min_cash_on_hand": 0,
        "headless": False,
        "show_scheduler": False,
        "debug_logging": False
    },
    "event_boss": {
        "enabled": False,
        "consume": {
            "Burger": False, "Coffee": False, "Egg": False, "Fries": False,
            "Lightning": False, "Milk": False, "Popcorn": False, "Watermelon": False,
        },
    },
    "case_work": {
        "enabled": False,
        "hospital": {
            "poll_interval": 31,
            "tasks": [
                {"type": "bionics",    "target": "all"},
                {"type": "sex_change", "target": "all"},
                {"type": "flu",        "target": "all"},
                {"type": "recover",    "target": "all"},
                {"type": "dna",        "enabled": True},
            ]
        },
        "fire": {
            "poll_interval": 31
        },
        "engineering": {
            "poll_interval": 31,
            "tasks": [
                {"type": "construct_apartment", "target": "all"},
                {"type": "repair_business",     "enabled": True},
                {"type": "repair_vehicle",      "target": "all"},
                {"type": "construct_vault",     "target": "all"},
            ]
        },
        "banking": {
            "poll_interval": 60
        }
    },
    "players": {
        "enabled": True,
        "refresh_interval_minutes": 30,
        "whitelist_bolds": True
    },
    "gym": {
        "enabled": False,
        "activity": "weights",
        "auto_travel": False,
    },
    "casino": {
        "enabled": False,
        "activity": "slots",
        "bet_amount": 100,
        "auto_travel": False,
    },
    "banking": {
        "auto_invest_enabled": False,
        "investment_term": "3,2.25",
        "invest_amount": 0,
    },
    "smart_travel": {
        "enabled": False,
        "store_priority": "bionics",       # "bionics" | "weapon" — overlap tie-break
        "window_vs_activity": "windows",   # "windows" | "activity"
        "home": "home_city",               # "home_city" | "Auckland" | "Beirut" | "Chicago"
    },
    "promo": {
        "monitor_top_job": False,
        "top_job_thread_id": "",
        "auto_promo": {"enabled": False},
        "choices": {
            "schooled": "A", "mule": "A", "hardrock": "A", "lifer": "A",
            "mayor": "B",
            "bank_teller": "A", "loan_officer": "A", "bank_manager": "A",
            "fire_fighter": "B", "fire_chief": "B",
            "mortician_assistant": "B", "mortician": "A", "funeral_director": "A",
            "nurse": "A", "doctor": "B", "surgeon": "B", "hospital_director": "A",
            "legal_secretary": "B", "lawyer": "B", "judge": "A", "supreme_court_judge": "B",
            "mechanic": "A", "technician": "B", "engineer": "B", "chief_engineer": "A",
            "supervisor": "A", "superintendent": "B", "commissioner_general": "A",
            "sergeant": "B", "senior_sergeant": "A", "detective": "B", "commissioner": "B",
            "dealer": "A", "giovane_dhonore": "A", "enforcer": "A", "piciotto": "A",
            "sgarrista": "A", "capodecima": "A", "caporegime": "A", "boss": "B", "don": "A",
        }
    },
    "crossroads": {
        "enabled": False,
        "selection": "current",   # "current" | "new"
    },
    "war_mode": {
        "enabled": False,
        "monitor_interval_minutes": 5,
        "skip_pin": False,
    },
    "consumables": {
        "timer_limit": "00:00",
        "auto_consume": False,
        "auto_consumable": "",
        "consumable_limit": 33,
        "buffer": 0,
        "smart_consumables": False
    },
    "jail": {
        "enabled": False,
        "duty": "laundry",
        "action": "gym",
        "use_consumables": False,
        "consumable": "cigarettes",
        "auto_jail_time": "off",
        "auto_jail_partner": "",
        "consumables_auto_off": False,
        "use_warrants": False,
        "auto_warrant_handling": "none",
        "jailbreak_execute_at": 0,
    },
    "character_history": {
        "enabled": False,
        "refresh_interval_minutes": 30,
        "obituary_last_run": 0
    },
    "bionics": {
        "enabled": False,
        "wanted_items": [],
        "priority_order": [],
        "check_interval_window_minutes": 5,      # check cadence while inside an active window
        "check_interval_no_window_minutes": 16,  # check cadence when window off / outside window
        "use_time_window": False,
        "window_start": "00:00",
        "window_end": "23:59",
        "auto_restock": False
    },
    "weapon_store": {
        "enabled": False,
        "wanted_items": [],
        "priority_order": [],
        "check_interval_window_minutes": 5,
        "check_interval_no_window_minutes": 16,
        "use_time_window": False,
        "window_start": "00:00",
        "window_end": "23:59",
        "auto_restock": False
    },
    "autobuy": {
        "enabled": False,
        "drugs": {
            "marijuana": {"max_price": 1000,  "max_qty": 9999},
            "ecstasy":   {"max_price": 5000,  "max_qty": 500},
            "acid":      {"max_price": 1000,  "max_qty": 0},
            "speed":     {"max_price": 1500,  "max_qty": 0},
            "pice":      {"max_price": 2000,  "max_qty": 0},
            "heroin":    {"max_price": 3000,  "max_qty": 400},
            "cocaine":   {"max_price": 4500,  "max_qty": 500}
        }
    },
    "sync": {
        "enabled": False,
        "server_url": "",
        "interval_minutes": 2,
        "sync_online_time": True,
        "sync_lists": True,
        "sync_groups": True,
    },
    "notifications": {
        "bionics_in_stock":        True,
        "bionics_purchased":       True,
        "bionics_restock":         False,
        "weapon_store_in_stock":   True,
        "weapon_store_purchased":  True,
        "weapon_store_restock":    False,
        "promotion_success":       True,
        "auto_promo":          True,
        "session_expired":     True,
        "cloudflare_detected": True,
        "jailed":              False,
        "targets_exhausted":   False,
        "mhs_protected":       True,
        "warrants_outstanding": True,
        "agg_not_available":   False,
        "dog_trains_unavailable": False,
    }
}

_lock = threading.Lock()


def _load_env() -> dict:
    """Load MM_EMAIL and MM_PASSWORD from .env file."""
    creds = {"email": "", "password": ""}
    if not os.path.exists(ENV_PATH):
        return creds
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            if key.strip() == "MM_EMAIL":
                creds["email"] = val.strip()
            elif key.strip() == "MM_PASSWORD":
                creds["password"] = val.strip()
    return creds


def get_env_var(key: str, default: str = "") -> str:
    """Read a single variable from the .env file, falling back to os.environ."""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if "=" not in line or line.startswith("#"):
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip()
    return os.environ.get(key, default)


def save_env(email: str, password: str, pin_required: bool = None, pin: str = None):
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            lines = f.readlines()
    managed = {"MM_EMAIL": email, "MM_PASSWORD": password}
    if pin_required is not None:
        managed["UI_PIN_REQUIRED"] = "true" if pin_required else "false"
    if pin is not None:
        managed["UI_PIN"] = pin
    seen = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in managed:
            new_lines.append(f"{key}={managed[key]}\n")
            seen.add(key)
        else:
            new_lines.append(line)
    for key, val in managed.items():
        if key not in seen:
            new_lines.append(f"{key}={val}\n")
    with _lock:
        with open(ENV_PATH, "w") as f:
            f.writelines(new_lines)


def get_pin_required() -> bool:
    return get_env_var("UI_PIN_REQUIRED", "false").lower() == "true"


def get_pin() -> str:
    return get_env_var("UI_PIN", "")


def get_or_create_secret_key() -> str:
    key = get_env_var("UI_SECRET_KEY", "")
    if key:
        return key
    import secrets
    key = secrets.token_hex(32)
    save_env_single("UI_SECRET_KEY", key)
    return key


def save_env_single(key: str, value: str):
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            lines = f.readlines()
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        k = stripped.split("=", 1)[0].strip()
        if k == key:
            new_lines.append(f"{key}={value}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}\n")
    with _lock:
        with open(ENV_PATH, "w") as f:
            f.writelines(new_lines)


def load():
    if not os.path.exists(CONFIG_PATH):
        save(DEFAULT_CONFIG)
        cfg = dict(DEFAULT_CONFIG)
    else:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
    cfg["credentials"] = _load_env()
    return cfg


def save(cfg):
    # Never write credentials to the JSON file
    safe = {k: v for k, v in cfg.items() if k != "credentials"}
    with _lock:
        with open(CONFIG_PATH, "w") as f:
            json.dump(safe, f, indent=2)
