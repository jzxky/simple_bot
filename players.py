"""
Player list management. Storage is handled by player_db (SQLite).
Public API is unchanged so bot.py / executor.py need no updates.
"""

import json
import time

import browser
import urls
import config as cfg
from tasks.base import Task
import player_db as _db

_db.init_db()

DEAD_CITIES = {"heaven", "hell", "locked"}
_DEFAULT_REFRESH_INTERVAL = 30 * 60


def _refresh_interval() -> int:
    minutes = cfg.load().get("players", {}).get("refresh_interval_minutes", 30)
    return max(1, int(minutes)) * 60


def load() -> dict:
    """Return legacy dict format for backward-compat (bot.py _should_payback etc.)."""
    players_list = _db.get_all_players()
    players_dict, agg, cw = {}, {}, {}
    for p in players_list:
        name = p["username"]
        players_dict[name] = {
            "username": name,
            "homecity": p["homecity"],
            "occupation": p["occupation"],
            "rank": p["rank"],
            "active": bool(p["active"]),
            "group": p["group_name"],
            "tags": p["tags"],
        }
        if p["agg_crimes"]:
            agg[name] = p["agg_crimes"]
        if p["case_work"]:
            cw[name] = p["case_work"]
    return {
        "players": players_dict,
        "lists": {"agg_crimes": agg, "case_work": cw},
        "groups": _db.get_groups(),
        "last_updated": _db.get_last_updated(),
    }


def refresh() -> int:
    """Fetch from updateusers.php, update SQLite. Returns active player count."""
    count, _marked = _refresh_impl()
    return count


def _refresh_impl() -> "tuple[int, int]":
    """Fetch from updateusers.php, update SQLite. Returns (active count, dead-marked count)."""
    try:
        browser.page().goto(
            urls.BASE_URL + "/skin/updateusers.php?q=1",
            wait_until="domcontentloaded", timeout=15000,
        )
        raw = json.loads(browser.page().inner_text("body"))
        browser.page().goto(urls.BASE_URL + "/main.asp", wait_until="domcontentloaded", timeout=15000)
    except Exception:
        return 0, 0

    seen = set()
    player_list = []
    for p in raw:
        name = p.get("userName", "")
        if not name:
            continue
        homecity   = p.get("userHomeCity", "")
        occupation = p.get("userOccupation", p.get("userJob", ""))
        rank       = p.get("userRank", "")
        is_dead    = homecity.lower() in DEAD_CITIES
        player_list.append({
            "username": name, "homecity": homecity,
            "occupation": occupation, "rank": rank, "active": not is_dead,
        })
        if not is_dead:
            seen.add(name)

    _db.upsert_players(player_list)

    marked = 0
    prev_active = _db.get_active_count()
    if prev_active > 0 and len(seen) < prev_active * 0.5:
        print(f"Player refresh: fetched list has only {len(seen)} active players "
              f"vs {prev_active} previously known — skipping dead-marking pass (suspect bad fetch).")
    else:
        marked = _db.mark_absent_dead(seen)

    return len(seen), marked


# Thin wrappers — delegate to player_db

def set_assignment(username: str, context: str, value: str):
    _db.set_assignment(username, context, value)


def set_player_group(username: str, group_name: str):
    _db.set_player_group(username, group_name)


def create_group(name: str, color: str, group_type: str = "neutral") -> bool:
    return _db.create_group(name, color, group_type)


def delete_group(name: str):
    _db.delete_group(name)


def update_group_color(name: str, color: str):
    _db.update_group_color(name, color)


def get_list(context: str) -> dict:
    store = load()
    return store["lists"].get(context, {})


def is_allowed(username: str, context: str, target_mode: str) -> bool:
    return _db.is_allowed(username, context, target_mode)


def group_mass_assign(group_name: str, context: str, assignment: str) -> int:
    players_list = _db.get_all_players()
    count = 0
    for p in players_list:
        if p["group_name"] == group_name:
            _db.set_assignment(p["username"], context, assignment)
            count += 1
    return count


# ---------------------------------------------------------------------------
# Background refresh task
# ---------------------------------------------------------------------------

class PlayerRefreshTask(Task):
    priority = 5
    label = "Player Refresh"

    def __init__(self):
        self._last_run: float = 0.0

    def can_run(self, state) -> bool:
        if not cfg.load().get("players", {}).get("enabled", True):
            return False
        return state.logged_in and time.monotonic() - self._last_run >= _refresh_interval()

    def run(self, state, executor):
        self._last_run = time.monotonic()
        count, marked = _refresh_impl()
        msg = f"Player list refreshed: {count} active players."
        if marked:
            msg += f" Marked {marked} absent player(s) as dead."
        state.add_log(msg)


class SyncTask(Task):
    priority = 6
    label = "Player Sync"

    def __init__(self):
        self._last_run: float = 0.0

    def _sync_cfg(self) -> dict:
        return cfg.load().get("sync", {})

    def can_run(self, state) -> bool:
        sc = self._sync_cfg()
        if not sc.get("enabled") or not sc.get("server_url", "").strip():
            return False
        interval = max(1, int(sc.get("interval_minutes", 2))) * 60
        return time.monotonic() - self._last_run >= interval

    def run(self, state, executor):
        import sync_client
        self._last_run = time.monotonic()
        sc = self._sync_cfg()
        url = sc.get("server_url", "").strip()
        try:
            sync_client.push_changes(url)
        except Exception as e:
            state.add_log(f"Sync push failed: {e}")
        try:
            sync_client.pull_changes(url)
        except Exception as e:
            state.add_log(f"Sync pull failed: {e}")
