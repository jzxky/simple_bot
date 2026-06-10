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
        "relog_on_session_expire": True
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
        }
    },
    "players": {
        "refresh_interval_minutes": 30
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


def save_env(email: str, password: str):
    with _lock:
        with open(ENV_PATH, "w") as f:
            f.write(f"MM_EMAIL={email}\n")
            f.write(f"MM_PASSWORD={password}\n")


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
