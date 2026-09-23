"""
war_hub_client.py — War mode integration with Player Hub.

Fetches war watch lists, reports WS changes, check updates, and business
ownership to the centralized Player Hub server.  All endpoints require an
API key configured in config.json under sync.api_key.
"""

import json
import logging
import urllib.request
import urllib.error

import config as cfg

log = logging.getLogger(__name__)


def _sync_cfg() -> dict:
    return cfg.load().get("sync", {})


def _base_url() -> str:
    return (_sync_cfg().get("server_url") or "").rstrip("/")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    api_key = _sync_cfg().get("api_key", "")
    if api_key:
        h["Authorization"] = f"Bearer {api_key}"
    return h


def _get(path: str) -> dict:
    url = _base_url() + path
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _post(path: str, payload: dict) -> dict:
    url = _base_url() + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def is_configured() -> bool:
    sc = _sync_cfg()
    return bool(sc.get("enabled")) and bool(sc.get("server_url")) and bool(sc.get("api_key"))


def fetch_war_lists() -> "dict | None":
    """Fetch current opps/friendlies watch lists from Player Hub.

    Returns {"opps": [...], "friendlies": [...]} or None on failure.
    """
    if not is_configured():
        return None
    try:
        return _get("/api/sync/war/lists")
    except Exception as e:
        log.warning("war_hub: fetch lists failed: %s", e)
        return None


def report_ws(records: list) -> bool:
    """Report WS changes (and optionally status/last_activity) for one or more names.

    Each record is a dict with at least "name" and "ws", and optionally
    "status" (alive|in-jail|in-max-jail|murdered) and "last_activity".
    The hub only records WS increases; decreases are ignored server-side.
    """
    if not is_configured() or not records:
        return False
    try:
        result = _post("/api/sync/war/record_ws", {"records": records})
        return result.get("ok", False)
    except Exception as e:
        log.warning("war_hub: report_ws failed: %s", e)
        return False


def report_check(name: str) -> bool:
    """Report that a player's profile was just checked (updates last_checked)."""
    if not is_configured() or not name:
        return False
    try:
        result = _post("/api/sync/war/check_update", {"name": name})
        return result.get("ok", False)
    except Exception as e:
        log.warning("war_hub: report_check failed: %s", e)
        return False


def report_online(city: str, names: list) -> bool:
    """Report the list of online players in a city."""
    if not is_configured() or not city:
        return False
    try:
        result = _post("/api/sync/war/online", {"city": city, "names": names})
        return result.get("ok", False)
    except Exception as e:
        log.warning("war_hub: report_online failed: %s", e)
        return False


def report_businesses(businesses: list) -> bool:
    """Report business ownership data.

    Each item: {"city": "...", "business_name": "...", "owner": "...", "available": bool}
    """
    if not is_configured() or not businesses:
        return False
    try:
        result = _post("/api/sync/war/businesses", {"businesses": businesses})
        return result.get("ok", False)
    except Exception as e:
        log.warning("war_hub: report_businesses failed: %s", e)
        return False


def report_jail(city: str, inmates: list) -> bool:
    """Report jail inmates for a city.

    inmates is a list of player name strings.
    """
    if not is_configured() or not city:
        return False
    try:
        result = _post("/api/sync/war/jail", {"city": city, "inmates": inmates})
        return result.get("ok", False)
    except Exception as e:
        log.warning("war_hub: report_jail failed: %s", e)
        return False


def report_home_cities(cities: list) -> bool:
    """Report home cities for war targets.

    Each item: {"name": "...", "city": "..."}
    """
    if not is_configured() or not cities:
        return False
    try:
        result = _post("/api/sync/war/home_cities", {"cities": cities})
        return result.get("ok", False)
    except Exception as e:
        log.warning("war_hub: report_home_cities failed: %s", e)
        return False
