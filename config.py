import json
import os
import threading

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG = {
    "credentials": {
        "email": "",
        "password": ""
    },
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


def load():
    if not os.path.exists(CONFIG_PATH):
        save(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save(cfg):
    with _lock:
        with open(CONFIG_PATH, "w") as f:
            json.dump(cfg, f, indent=2)
