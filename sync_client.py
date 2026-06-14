"""
sync_client.py — Push local changes to and pull remote changes from a sync server.

Designed for use by the SyncTask background task in players.py.
Does not re-stamp timestamps on pulled data to prevent echo loops.
"""

import json
import urllib.request
import urllib.error

import player_db as _db

_PUSH_TS_KEY  = "sync_last_pushed_at"
_PULL_TS_KEY  = "sync_last_pulled_at"
_EPOCH        = "1970-01-01T00:00:00Z"


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
    since = _db.get_sync_meta(_PUSH_TS_KEY) or _EPOCH
    players = _db.get_players_since(since)
    groups  = _db.get_groups_since(since)
    career  = _db.get_career_since(since)

    if not players and not groups and not career:
        return

    result = _post(server_url.rstrip("/") + "/sync/push", {
        "players": players,
        "groups":  groups,
        "career":  career,
    })
    if result.get("ok"):
        _db.set_sync_meta(_PUSH_TS_KEY, result.get("server_time", _db._utcnow()))


def pull_changes(server_url: str):
    """Pull records changed on the server since last pull and apply them locally."""
    since = _db.get_sync_meta(_PULL_TS_KEY) or _EPOCH
    url = server_url.rstrip("/") + f"/sync/pull?since={since}"
    data = _get(url)

    if data.get("players"):
        _db.apply_synced_players(data["players"])
    if data.get("groups"):
        _db.apply_synced_groups(data["groups"])
    if data.get("career"):
        _db.apply_synced_career(data["career"])

    server_time = data.get("server_time")
    if server_time:
        _db.set_sync_meta(_PULL_TS_KEY, server_time)
