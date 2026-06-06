import json
import os
import threading

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

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
        "secondary": {
            "crime": "pickpocket",
            "energy_threshold": 50
        }
    },
    "action": {
        "enabled": True,
        "type": "community_service",
        "sub_option": ""
    },
    "payback_enabled": True,
    "career_training": {
        "career": "fire"
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
