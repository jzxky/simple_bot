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
EXCLUDED_CITIES = {"manila"}
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
    """Refresh the local player list. Returns active player count.
    With Player Hub configured this mirrors the hub (which decides births and
    deaths); otherwise it fetches updateusers.php and updates SQLite."""
    import sync_client
    if sync_client.hub_managed():
        sync_client.mirror_from_hub()
        return _db.get_active_count()
    count, _marked = _refresh_impl()
    return count


def fetch_skins_raw() -> "list | None":
    """Fetch the updateusers.php JSON list unchanged. None on failure."""
    try:
        browser.page().goto(
            urls.BASE_URL + "/skin/updateusers.php?q=1",
            wait_until="domcontentloaded", timeout=15000,
        )
        raw = json.loads(browser.page().inner_text("body"))
        browser.page().goto(urls.BASE_URL + "/main.asp", wait_until="domcontentloaded", timeout=15000)
        browser.record_nav_success()
    except Exception as e:
        err = str(e)
        if any(kw in err for kw in ("Timeout", "net::", "ERR_")):
            browser.record_nav_failure()
        return None
    return raw if isinstance(raw, list) else None


def _refresh_impl() -> "tuple[int, int]":
    """Fetch from updateusers.php, update SQLite. Returns (active count, dead-marked count)."""
    raw = fetch_skins_raw()
    if raw is None:
        return 0, 0

    seen = set()
    player_list = []
    pic_urls = []
    for p in raw:
        name = p.get("userName", "")
        if not name:
            continue
        homecity   = p.get("userHomeCity", "")
        if homecity.lower() in EXCLUDED_CITIES:
            continue
        occupation = p.get("userOccupation", p.get("userJob", ""))
        rank       = p.get("userRank", "")
        pic_url    = p.get("userPicLink", "")
        is_dead    = homecity.lower() in DEAD_CITIES
        player_list.append({
            "username": name, "homecity": homecity,
            "occupation": occupation, "rank": rank, "active": not is_dead,
            "pic_url": pic_url,
        })
        if pic_url:
            pic_urls.append(pic_url)
        if not is_dead:
            seen.add(name)

    _db.upsert_players(player_list)
    _download_player_images(pic_urls)

    marked = 0
    prev_active = _db.get_active_count()
    if prev_active > 0 and len(seen) < prev_active * 0.5:
        print(f"Player refresh: fetched list has only {len(seen)} active players "
              f"vs {prev_active} previously known — skipping dead-marking pass (suspect bad fetch).")
    else:
        marked = _db.mark_absent_dead(seen)

    return len(seen), marked


def download_player_images(raw: list):
    """Cache avatars for every entry in a raw updateusers.php list."""
    _download_player_images([p.get("userPicLink", "") for p in raw if p.get("userPicLink")])


def _download_player_images(pic_urls: list):
    """Download unique player avatars not already cached, reusing the browser's
    authenticated request context. Failures are best-effort/non-fatal."""
    if not pic_urls:
        return
    try:
        import player_images as _pi
    except Exception:
        return

    def _fetch(url):
        try:
            resp = browser.page().request.get(url, timeout=15000)
            if resp.ok:
                return resp.body()
        except Exception:
            return None
        return None

    try:
        n = _pi.download_missing(pic_urls, _fetch)
        if n:
            print(f"[players] Downloaded {n} new player image(s).")
    except Exception as e:
        print(f"[players] Image download error: {e}")


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
        import sync_client
        if not cfg.load().get("players", {}).get("enabled", True):
            return False
        if sync_client.hub_managed():
            return False  # the hub decides births/deaths; SyncTask mirrors it
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
        if sync_client.hub_managed():
            try:
                r = sync_client.mirror_from_hub()
                if r["players"] or r["removed"] or r["career"] or r["groups_removed"]:
                    state.add_log(f"Hub sync: {r['players']} player(s) updated, {r['removed']} removed, "
                                  f"{r['career']} career row(s).")
            except Exception as e:
                state.add_log(f"Hub sync failed: {e}")
            return
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
