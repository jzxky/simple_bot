"""
sync_client.py — Push local changes to and pull remote changes from a sync server.

Designed for use by the SyncTask background task in players.py.
Does not re-stamp timestamps on pulled data to prevent echo loops.
"""

import json
import urllib.request
import urllib.error

import config as cfg
import player_db as _db

_PUSH_TS_KEY  = "sync_last_pushed_at"
_PULL_TS_KEY  = "sync_last_pulled_at"
_GROUPS_RECONCILED_KEY = "sync_groups_reconciled"
_EPOCH        = "1970-01-01T00:00:00Z"


def _sync_cfg() -> dict:
    return cfg.load().get("sync", {})


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def _get(url: str) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def push_changes(server_url: str):
    """Push all locally modified records since last push to the sync server."""
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

    result = _post(server_url.rstrip("/") + "/sync/push", payload)
    if result.get("ok"):
        _db.set_sync_meta(_PUSH_TS_KEY, result.get("server_time", _db._utcnow()))


def _reconcile_groups(server_url: str):
    """Full group reconciliation: server wins. Push local-only groups up."""
    url = server_url.rstrip("/") + "/sync/groups/full"
    try:
        data = _get(url)
    except urllib.error.HTTPError:
        return
    server_groups = {g["name"]: g for g in data.get("groups", [])}
    local_groups = {g["name"]: g for g in _db.get_all_groups()}

    for name, sg in server_groups.items():
        if name in local_groups:
            _db.apply_synced_groups([sg])
        else:
            _db.apply_synced_groups([sg])

    local_only = []
    for name, lg in local_groups.items():
        if name not in server_groups:
            local_only.append(lg)
    if local_only:
        _post(server_url.rstrip("/") + "/sync/push", {
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
    url = server_url.rstrip("/") + f"/sync/pull?since={since}"
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
