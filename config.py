import json
import os
import threading
import paths

CONFIG_PATH = os.path.join(paths.data_dir(), "config.json")
ENV_PATH = os.path.join(paths.data_dir(), ".env")

DEFAULT_CONFIG = {
    "earns": {
        "enabled": True,
        "category": "Hospital",
        "earn_type": "surgeon",
        "check_interval_minutes": 30
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
        "fallback_to_away": False
    },
    "action": {
        "enabled": True,
        "type": "community_service",
        "sub_option": ""
    },
    "away_action": {
        "enabled": False,
        "type": "drug_manufacturing"
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
            "poll_interval": 31
        }
    },
    "players": {
        "enabled": True,
        "refresh_interval_minutes": 30
    },
    "gym": {
        "enabled": False,
        "activity": "weights",
        "auto_travel": False,
    },
    "promo": {
        "monitor_top_job": False,
        "top_job_thread_id": ""
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
        "consumable": "cigarettes"
    },
    "character_history": {
        "enabled": False,
        "refresh_interval_minutes": 30
    },
    "bionics": {
        "enabled": False,
        "wanted_items": [],
        "check_interval_minutes": 5,
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


def save_env(email: str, password: str):
    # Read existing .env, update only MM_EMAIL/MM_PASSWORD, preserve all other lines
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            lines = f.readlines()
    managed = {"MM_EMAIL": email, "MM_PASSWORD": password}
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
