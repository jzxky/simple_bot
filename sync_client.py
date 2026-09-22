"""
sync_client.py — Push local changes to and pull remote changes from Player Hub.

Designed for use by the SyncTask background task in players.py.
Does not re-stamp timestamps on pulled data to prevent echo loops.
All endpoints use /api/sync/* paths with Bearer API key auth.
"""

import json
import logging
import urllib.request
import urllib.error

import config as cfg
import player_db as _db

log = logging.getLogger(__name__)

_PUSH_TS_KEY  = "sync_last_pushed_at"
_PULL_TS_KEY  = "sync_last_pulled_at"
_GROUPS_RECONCILED_KEY = "sync_groups_reconciled"
_EPOCH        = "1970-01-01T00:00:00Z"


def _sync_cfg() -> dict:
    return cfg.load().get("sync", {})


def _auth_headers() -> dict:
    sc = _sync_cfg()
    headers = {"Content-Type": "application/json"}
    api_key = sc.get("api_key", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers=_auth_headers(),
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_auth_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def health_check(server_url: str) -> "dict | None":
    """Check hub health. Returns {"ok": true, "player_count": N} or None."""
    try:
        return _get(server_url.rstrip("/") + "/api/sync/health")
    except Exception as e:
        log.warning("sync health check failed: %s", e)
        return None


def push_changes(server_url: str):
    """Push all locally modified records since last push to Player Hub."""
    sc = _sync_cfg()
    since = _db.get_sync_meta(_PUSH_TS_KEY) or _EPOCH
    players = _db.get_players_since(since) if sc.get("sync_lists", True) else []
    groups  = _db.get_groups_since(since) if sc.get("sync_groups", True) else []
    career  = _db.get_career_since(since) if sc.get("sync_lists", True) else []

    if not players and not groups and not career:
        return

    payload = {"players": players, "groups": groups, "career": career}
    if not sc.get("sync_online_time", True):
        for p in payload["players"]:
            p.pop("character_age", None)
            p.pop("jail_age", None)

    result = _post(server_url.rstrip("/") + "/api/sync/push", payload)
    if result.get("ok"):
        _db.set_sync_meta(_PUSH_TS_KEY, result.get("server_time", _db._utcnow()))


def _reconcile_groups(server_url: str):
    """Full group reconciliation: server wins. Push local-only groups up."""
    url = server_url.rstrip("/") + "/api/sync/groups/full"
    try:
        data = _get(url)
    except urllib.error.HTTPError:
        return
    server_groups = {g["name"]: g for g in data.get("groups", [])}
    local_groups = {g["name"]: g for g in _db.get_all_groups()}

    for name, sg in server_groups.items():
        _db.apply_synced_groups([sg])

    local_only = []
    for name, lg in local_groups.items():
        if name not in server_groups:
            local_only.append(lg)
    if local_only:
        _post(server_url.rstrip("/") + "/api/sync/push", {
            "players": [], "groups": local_only, "career": [],
        })


def pull_changes(server_url: str):
    """Pull records changed on the server since last pull and apply them locally."""
    sc = _sync_cfg()

    if sc.get("sync_groups", True):
        reconciled_url = _db.get_sync_meta(_GROUPS_RECONCILED_KEY)
        if reconciled_url != server_url:
            _reconcile_groups(server_url)
            _db.set_sync_meta(_GROUPS_RECONCILED_KEY, server_url)

    since = _db.get_sync_meta(_PULL_TS_KEY) or _EPOCH
    url = server_url.rstrip("/") + f"/api/sync/pull?since={since}"
    data = _get(url)

    if data.get("players") and sc.get("sync_lists", True):
        players = data["players"]
        if not sc.get("sync_online_time", True):
            for p in players:
                p.pop("character_age", None)
                p.pop("jail_age", None)
        _db.apply_synced_players(players)
    if data.get("groups") and sc.get("sync_groups", True):
        _db.apply_synced_groups(data["groups"])
    if data.get("career") and sc.get("sync_lists", True):
        _db.apply_synced_career(data["career"])

    server_time = data.get("server_time")
    if server_time:
        _db.set_sync_meta(_PULL_TS_KEY, server_time)


def update_respect(server_url: str, username: str, respect: str) -> bool:
    """Report a player's respect value to Player Hub."""
    try:
        result = _post(
            server_url.rstrip("/") + "/api/sync/players/update_respect",
            {"username": username, "respect": respect},
        )
        return result.get("ok", False)
    except Exception as e:
        log.warning("sync update_respect failed for %s: %s", username, e)
        return False


def update_homecity(server_url: str, username: str, homecity: str) -> bool:
    """Report a player's home city change to Player Hub."""
    try:
        result = _post(
            server_url.rstrip("/") + "/api/sync/players/update_homecity",
            {"username": username, "homecity": homecity},
        )
        return result.get("ok", False)
    except Exception as e:
        log.warning("sync update_homecity failed for %s: %s", username, e)
        return False
