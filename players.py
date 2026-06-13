"""
Player list management: fetch, merge, and persist the active player roster.
Stores players.json in data_dir(). Auto-refreshed every 30 minutes by the bot.
"""

import json
import os
import threading
import time
from datetime import datetime
import paths
import browser
import urls
import config as cfg
from tasks.base import Task

PLAYERS_PATH = os.path.join(paths.data_dir(), "players.json")
DEAD_CITIES = {"heaven", "hell", "locked"}
_DEFAULT_REFRESH_INTERVAL = 30 * 60  # seconds


def _refresh_interval() -> int:
    minutes = cfg.load().get("players", {}).get("refresh_interval_minutes", 30)
    return max(1, int(minutes)) * 60

_lock = threading.Lock()


def _empty_store() -> dict:
    return {"players": {}, "lists": {"agg_crimes": {}, "case_work": {}}, "groups": [], "last_updated": None}


def load() -> dict:
    if not os.path.exists(PLAYERS_PATH):
        return _empty_store()
    try:
        with open(PLAYERS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return _empty_store()


def _save(store: dict):
    with _lock:
        with open(PLAYERS_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)


def refresh() -> int:
    """Fetch player list from game, merge with store. Returns number of active players."""
    try:
        browser.page().goto(urls.BASE_URL + "/skin/updateusers.php?q=1", wait_until="domcontentloaded", timeout=15000)
        raw = json.loads(browser.page().inner_text("body"))
        browser.page().goto(urls.BASE_URL + "/main.asp", wait_until="domcontentloaded", timeout=15000)
    except Exception:
        return 0

    store = load()
    players = store.setdefault("players", {})
    seen = set()

    for p in raw:
        name = p.get("userName", "")
        if not name:
            continue
        homecity = p.get("userHomeCity", "")
        is_dead = homecity.lower() in DEAD_CITIES

        entry = players.get(name, {"username": name})
        entry["homecity"] = homecity
        entry["occupation"] = p.get("userOccupation", p.get("userJob", ""))
        entry["rank"] = p.get("userRank", "")
        entry["active"] = not is_dead
        players[name] = entry
        if not is_dead:
            seen.add(name)

    # Mark players absent from this fetch as inactive only if confirmed dead
    # Players in jail or otherwise missing from the fetch keep their last known status
    for name, entry in players.items():
        if name not in seen and entry.get("active", True):
            city = entry.get("homecity", "").lower()
            if city in DEAD_CITIES:
                entry["active"] = False

    store["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save(store)
    return len(seen)


def set_assignment(username: str, context: str, value: str):
    """Set 'whitelist', 'blacklist', or '' (none) for a player in a given context."""
    store = load()
    lists = store.setdefault("lists", {"agg_crimes": {}, "case_work": {}})
    ctx = lists.setdefault(context, {})
    if value:
        ctx[username] = value
    else:
        ctx.pop(username, None)
    _save(store)


def create_group(name: str, color: str) -> bool:
    """Create a new group. Returns False if name already exists."""
    store = load()
    groups = store.setdefault("groups", [])
    if any(g["name"] == name for g in groups):
        return False
    groups.append({"name": name, "color": color or "#888888"})
    _save(store)
    return True


def delete_group(name: str):
    """Delete a group and unset it from all members."""
    store = load()
    store["groups"] = [g for g in store.get("groups", []) if g["name"] != name]
    for player in store["players"].values():
        if player.get("group") == name:
            player.pop("group", None)
    _save(store)


def update_group_color(name: str, color: str):
    """Update the color of an existing group."""
    store = load()
    for g in store.get("groups", []):
        if g["name"] == name:
            g["color"] = color
            break
    _save(store)


def set_player_group(username: str, group_name: str):
    """Assign a player to a group, or clear if group_name is empty."""
    store = load()
    player = store["players"].get(username)
    if player is None:
        return
    if group_name:
        player["group"] = group_name
    else:
        player.pop("group", None)
    _save(store)


def group_mass_assign(group_name: str, context: str, assignment: str) -> int:
    """Apply an assignment to all players in a group. Returns count updated."""
    store = load()
    ctx = store.setdefault("lists", {}).setdefault(context, {})
    count = 0
    for name, player in store["players"].items():
        if player.get("group") == group_name:
            if assignment:
                ctx[name] = assignment
            else:
                ctx.pop(name, None)
            count += 1
    _save(store)
    return count


def get_list(context: str) -> dict:
    """Return {username: 'whitelist'|'blacklist'} for the given context."""
    return load()["lists"].get(context, {})


def is_allowed(username: str, context: str, target_mode: str) -> bool:
    """
    Check if username is allowed given target_mode:
      'all'          — always allowed
      'whitelist'    — only if on whitelist
      'not_blacklist'— allowed unless on blacklist
      'none'         — never allowed
    """
    if target_mode == "none":
        return False
    if target_mode == "all":
        return True
    lst = get_list(context)
    assignment = lst.get(username, "")
    if target_mode == "whitelist":
        return assignment == "whitelist"
    if target_mode == "not_blacklist":
        return assignment != "blacklist"
    return True


# ---------------------------------------------------------------------------
# Background refresh task
# ---------------------------------------------------------------------------

class PlayerRefreshTask(Task):
    """Runs in the bot scheduler — refreshes player list every 30 minutes."""
    priority = 5  # low priority, runs in background
    label = 'Player Refresh'

    def __init__(self):
        self._last_run: float = 0.0

    def can_run(self, state) -> bool:
        if not cfg.load().get("players", {}).get("enabled", True):
            return False
        return state.logged_in and time.monotonic() - self._last_run >= _refresh_interval()

    def run(self, state, executor):
        self._last_run = time.monotonic()
        count = refresh()
        state.add_log(f"Player list refreshed: {count} active players.")
