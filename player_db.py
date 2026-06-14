"""
player_db.py — SQLite-backed player store.

Tables:
  players        — current state per player
  career_history — append-only change log (one row per state change)
  groups         — group definitions (with type, agg/cw assignments)
  meta           — key/value (e.g. last_updated)
"""

import os
import json
import sqlite3
import threading
from datetime import datetime, timezone

import paths

DB_PATH = os.path.join(paths.data_dir(), "players.db")
# Players with these home cities are never stored — not even as inactive
_SKIP_CITIES = {"heaven", "hell", "locked"}
_DEAD_CITIES  = _SKIP_CITIES  # kept for mark_absent_dead compat

_lock = threading.Lock()

CAREER_TAGS = [
    {"tag": "CM3", "requires_all": {"Fire Chief", "Hospital Director"}},
    {"tag": "TX",  "requires_any": {"Commissioner-General"}},
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    username      TEXT PRIMARY KEY,
    homecity      TEXT DEFAULT '',
    occupation    TEXT DEFAULT '',
    rank          TEXT DEFAULT '',
    active        INTEGER DEFAULT 1,
    group_name    TEXT DEFAULT '',
    agg_crimes    TEXT DEFAULT '',
    case_work     TEXT DEFAULT '',
    character_age INTEGER DEFAULT 0,
    jail_age      INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS career_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    ts         TEXT NOT NULL,
    rank       TEXT DEFAULT '',
    occupation TEXT DEFAULT '',
    homecity   TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS groups (
    name      TEXT PRIMARY KEY,
    color     TEXT DEFAULT '#3498db',
    type      TEXT DEFAULT 'neutral',
    agg_crimes TEXT DEFAULT '',
    case_work  TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_career_username ON career_history(username);
"""

# Columns added after initial release — applied via ALTER TABLE if missing
_MIGRATIONS = [
    ("players",  "character_age",          "INTEGER DEFAULT 0"),
    ("players",  "jail_age",               "INTEGER DEFAULT 0"),
    ("groups",   "type",                   "TEXT DEFAULT 'neutral'"),
    ("groups",   "agg_crimes",             "TEXT DEFAULT ''"),
    ("groups",   "case_work",              "TEXT DEFAULT ''"),
    # Sync timestamps
    ("players",  "assignments_updated_at", "TEXT DEFAULT ''"),
    ("players",  "scraped_at",             "TEXT DEFAULT ''"),
    ("groups",   "updated_at",             "TEXT DEFAULT ''"),
]


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _apply_migrations(con: sqlite3.Connection):
    for table, col, col_def in _MIGRATIONS:
        existing = {r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
    con.commit()


def init_db():
    with _lock:
        con = _conn()
        try:
            con.executescript(_SCHEMA)
            con.commit()
            _apply_migrations(con)
            _migrate_json(con)
        finally:
            con.close()


def _migrate_json(con: sqlite3.Connection):
    count = con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    if count > 0:
        return
    json_path = os.path.join(paths.data_dir(), "players.json")
    if not os.path.exists(json_path):
        return
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            store = json.load(f)
    except Exception:
        return

    for g in store.get("groups", []):
        con.execute(
            "INSERT OR IGNORE INTO groups (name, color) VALUES (?, ?)",
            (g["name"], g.get("color", "#3498db")),
        )

    lists  = store.get("lists", {})
    agg_map = lists.get("agg_crimes", {})
    cw_map  = lists.get("case_work", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for name, p in store.get("players", {}).items():
        homecity = p.get("homecity", "")
        if homecity.lower() in _SKIP_CITIES:
            continue
        active     = 1 if p.get("active", True) else 0
        occupation = p.get("occupation", "")
        rank       = p.get("rank", "")
        group_name = p.get("group", "")
        con.execute(
            """INSERT OR IGNORE INTO players
               (username, homecity, occupation, rank, active, group_name, agg_crimes, case_work)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, homecity, occupation, rank, active, group_name,
             agg_map.get(name, ""), cw_map.get(name, "")),
        )
        if homecity or occupation or rank:
            con.execute(
                "INSERT INTO career_history (username, ts, rank, occupation, homecity) VALUES (?, ?, ?, ?, ?)",
                (name, ts, rank, occupation, homecity),
            )

    last_updated = store.get("last_updated")
    if last_updated:
        con.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_updated', ?)",
            (last_updated,),
        )
    con.commit()
    print("[player_db] Migrated players.json → players.db")


# ---------------------------------------------------------------------------
# Tag helpers
# ---------------------------------------------------------------------------

def _compute_tags(username: str, con: sqlite3.Connection) -> list:
    rows = con.execute(
        "SELECT DISTINCT occupation FROM career_history WHERE username = ?",
        (username,),
    ).fetchall()
    cur = con.execute(
        "SELECT occupation FROM players WHERE username = ?", (username,)
    ).fetchone()
    all_occ = {r["occupation"] for r in rows} | ({cur["occupation"]} if cur else set())
    tags = []
    for td in CAREER_TAGS:
        if "requires_all" in td and td["requires_all"].issubset(all_occ):
            tags.append(td["tag"])
        elif "requires_any" in td and td["requires_any"] & all_occ:
            tags.append(td["tag"])
    return tags


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def get_all_players() -> list:
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                """SELECT username, homecity, occupation, rank, active,
                          group_name, agg_crimes, case_work,
                          character_age, jail_age
                   FROM players ORDER BY username COLLATE NOCASE"""
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["tags"] = _compute_tags(r["username"], con)
                result.append(d)
            return result
        finally:
            con.close()


def get_players_by_group(group_name: str) -> list:
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                """SELECT username, homecity, occupation, rank, active,
                          group_name, agg_crimes, case_work,
                          character_age, jail_age
                   FROM players WHERE group_name=?
                   ORDER BY username COLLATE NOCASE""",
                (group_name,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["tags"] = _compute_tags(r["username"], con)
                result.append(d)
            return result
        finally:
            con.close()


def get_career_history(username: str) -> list:
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                """SELECT ts, rank, occupation, homecity
                   FROM career_history WHERE username = ?
                   ORDER BY id DESC""",
                (username,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()


def get_groups() -> list:
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                "SELECT name, color, type, agg_crimes, case_work FROM groups ORDER BY name"
            ).fetchall()
            groups = []
            for r in rows:
                g = dict(r)
                g["member_count"] = con.execute(
                    "SELECT COUNT(*) FROM players WHERE group_name=?", (g["name"],)
                ).fetchone()[0]
                groups.append(g)
            return groups
        finally:
            con.close()


def get_last_updated() -> "str | None":
    with _lock:
        con = _conn()
        try:
            row = con.execute("SELECT value FROM meta WHERE key='last_updated'").fetchone()
            return row["value"] if row else None
        finally:
            con.close()


def get_active_count() -> int:
    with _lock:
        con = _conn()
        try:
            return con.execute("SELECT COUNT(*) FROM players WHERE active=1").fetchone()[0]
        finally:
            con.close()


def get_usernames() -> list:
    with _lock:
        con = _conn()
        try:
            return [r[0] for r in con.execute("SELECT username FROM players").fetchall()]
        finally:
            con.close()


def get_assignment(username: str, context: str) -> str:
    col = "agg_crimes" if context == "agg_crimes" else "case_work"
    with _lock:
        con = _conn()
        try:
            row = con.execute(f"SELECT {col} FROM players WHERE username=?", (username,)).fetchone()
            return row[0] if row else ""
        finally:
            con.close()


def get_group_assignment(group_name: str, context: str) -> str:
    col = "agg_crimes" if context == "agg_crimes" else "case_work"
    if not group_name:
        return ""
    with _lock:
        con = _conn()
        try:
            row = con.execute(f"SELECT {col} FROM groups WHERE name=?", (group_name,)).fetchone()
            return row[0] if row else ""
        finally:
            con.close()


def get_player_group(username: str) -> str:
    with _lock:
        con = _conn()
        try:
            row = con.execute("SELECT group_name FROM players WHERE username=?", (username,)).fetchone()
            return row[0] if row else ""
        finally:
            con.close()


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def upsert_players(player_list: list):
    """Update player records. Skips Heaven/Hell players entirely.
    Appends career_history when rank/occupation/homecity changes."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scraped_at = _utcnow()
    with _lock:
        con = _conn()
        try:
            for p in player_list:
                name     = p["username"]
                homecity = p.get("homecity", "")
                if homecity.lower() in _SKIP_CITIES:
                    continue
                occupation = p.get("occupation", "")
                rank       = p.get("rank", "")
                active     = 1 if p.get("active", True) else 0

                cur = con.execute(
                    "SELECT homecity, occupation, rank FROM players WHERE username=?", (name,)
                ).fetchone()
                changed = (cur is None or
                           cur["homecity"] != homecity or
                           cur["occupation"] != occupation or
                           cur["rank"] != rank)

                con.execute(
                    """INSERT INTO players (username, homecity, occupation, rank, active, scraped_at)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(username) DO UPDATE SET
                           homecity=excluded.homecity,
                           occupation=excluded.occupation,
                           rank=excluded.rank,
                           active=excluded.active,
                           scraped_at=excluded.scraped_at""",
                    (name, homecity, occupation, rank, active, scraped_at),
                )
                if changed:
                    con.execute(
                        "INSERT INTO career_history (username, ts, rank, occupation, homecity) VALUES (?,?,?,?,?)",
                        (name, ts, rank, occupation, homecity),
                    )

            con.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_updated', ?)", (ts,)
            )
            con.commit()
        finally:
            con.close()


def mark_absent_dead(seen_names: set):
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                "SELECT username, homecity FROM players WHERE active=1"
            ).fetchall()
            for r in rows:
                if r["username"] not in seen_names and r["homecity"].lower() in _DEAD_CITIES:
                    con.execute("UPDATE players SET active=0 WHERE username=?", (r["username"],))
            con.commit()
        finally:
            con.close()


def increment_ages(online_names: set, jailed_names: set, minutes: int = 30):
    """Increment character_age or jail_age for known online players."""
    with _lock:
        con = _conn()
        try:
            for name in jailed_names:
                con.execute(
                    "UPDATE players SET jail_age=jail_age+? WHERE username=?", (minutes, name)
                )
            for name in online_names - jailed_names:
                con.execute(
                    "UPDATE players SET character_age=character_age+? WHERE username=?", (minutes, name)
                )
            con.commit()
        finally:
            con.close()


def set_assignment(username: str, context: str, value: str):
    col = "agg_crimes" if context == "agg_crimes" else "case_work"
    ts = _utcnow()
    with _lock:
        con = _conn()
        try:
            con.execute(
                f"UPDATE players SET {col}=?, assignments_updated_at=? WHERE username=?",
                (value, ts, username),
            )
            con.commit()
        finally:
            con.close()


def bulk_set_assignment(usernames: list, context: str, value: str):
    col = "agg_crimes" if context == "agg_crimes" else "case_work"
    ts = _utcnow()
    with _lock:
        con = _conn()
        try:
            con.executemany(
                f"UPDATE players SET {col}=?, assignments_updated_at=? WHERE username=?",
                [(value, ts, u) for u in usernames],
            )
            con.commit()
        finally:
            con.close()


def set_player_group(username: str, group_name: str):
    ts = _utcnow()
    with _lock:
        con = _conn()
        try:
            con.execute(
                "UPDATE players SET group_name=?, assignments_updated_at=? WHERE username=?",
                (group_name, ts, username),
            )
            con.commit()
        finally:
            con.close()


def create_group(name: str, color: str, group_type: str = "neutral") -> bool:
    ts = _utcnow()
    with _lock:
        con = _conn()
        try:
            try:
                con.execute(
                    "INSERT INTO groups (name, color, type, updated_at) VALUES (?, ?, ?, ?)",
                    (name, color or "#3498db", group_type, ts),
                )
                con.commit()
                return True
            except sqlite3.IntegrityError:
                return False
        finally:
            con.close()


def delete_group(name: str):
    with _lock:
        con = _conn()
        try:
            con.execute("DELETE FROM groups WHERE name=?", (name,))
            con.execute("UPDATE players SET group_name='' WHERE group_name=?", (name,))
            con.commit()
        finally:
            con.close()


def update_group_color(name: str, color: str):
    ts = _utcnow()
    with _lock:
        con = _conn()
        try:
            con.execute("UPDATE groups SET color=?, updated_at=? WHERE name=?", (color, ts, name))
            con.commit()
        finally:
            con.close()


def update_group_type(name: str, group_type: str):
    ts = _utcnow()
    with _lock:
        con = _conn()
        try:
            con.execute("UPDATE groups SET type=?, updated_at=? WHERE name=?", (group_type, ts, name))
            con.commit()
        finally:
            con.close()


def update_group_assignment(name: str, context: str, value: str):
    col = "agg_crimes" if context == "agg_crimes" else "case_work"
    ts = _utcnow()
    with _lock:
        con = _conn()
        try:
            con.execute(f"UPDATE groups SET {col}=?, updated_at=? WHERE name=?", (value, ts, name))
            con.commit()
        finally:
            con.close()


# ---------------------------------------------------------------------------
# Sync helpers — read changed rows / apply pulled rows without re-stamping
# ---------------------------------------------------------------------------

_EPOCH = "1970-01-01T00:00:00Z"


def get_players_since(ts: str) -> list:
    """Return player rows modified (scraped or assignment-changed) since ts."""
    since = ts or _EPOCH
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                """SELECT username, homecity, occupation, rank, active,
                          group_name, agg_crimes, case_work,
                          character_age, jail_age,
                          assignments_updated_at, scraped_at
                   FROM players
                   WHERE COALESCE(assignments_updated_at, '') > ?
                      OR COALESCE(scraped_at, '') > ?""",
                (since, since),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()


def get_groups_since(ts: str) -> list:
    """Return group rows modified since ts."""
    since = ts or _EPOCH
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                """SELECT name, color, type, agg_crimes, case_work, updated_at
                   FROM groups WHERE COALESCE(updated_at, '') > ?""",
                (since,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()


def get_career_since(ts: str) -> list:
    """Return career_history rows with ts > since."""
    since = ts or _EPOCH
    with _lock:
        con = _conn()
        try:
            rows = con.execute(
                "SELECT username, ts, rank, occupation, homecity FROM career_history WHERE ts > ?",
                (since,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            con.close()


def apply_synced_players(rows: list):
    """Merge pulled player rows without re-stamping timestamps (prevents echo loops).
    Ages use MAX; scrape fields use scraped_at gating; assignment fields use
    assignments_updated_at gating."""
    with _lock:
        con = _conn()
        try:
            for r in rows:
                name = r.get("username")
                if not name:
                    continue
                cur = con.execute(
                    """SELECT homecity, occupation, rank, active,
                              group_name, agg_crimes, case_work,
                              character_age, jail_age,
                              assignments_updated_at, scraped_at
                       FROM players WHERE username=?""",
                    (name,),
                ).fetchone()

                incoming_scraped = r.get("scraped_at") or ""
                incoming_assign  = r.get("assignments_updated_at") or ""

                if cur is None:
                    # New player — insert everything as-is
                    con.execute(
                        """INSERT INTO players
                           (username, homecity, occupation, rank, active,
                            group_name, agg_crimes, case_work,
                            character_age, jail_age,
                            assignments_updated_at, scraped_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (name,
                         r.get("homecity", ""), r.get("occupation", ""),
                         r.get("rank", ""), r.get("active", 1),
                         r.get("group_name", ""), r.get("agg_crimes", ""),
                         r.get("case_work", ""),
                         r.get("character_age", 0), r.get("jail_age", 0),
                         incoming_assign, incoming_scraped),
                    )
                else:
                    local_scraped = cur["scraped_at"] or ""
                    local_assign  = cur["assignments_updated_at"] or ""

                    # Scrape fields: only overwrite if incoming scraped_at is newer
                    if incoming_scraped > local_scraped:
                        con.execute(
                            """UPDATE players SET homecity=?, occupation=?, rank=?, active=?,
                               scraped_at=? WHERE username=?""",
                            (r.get("homecity", cur["homecity"]),
                             r.get("occupation", cur["occupation"]),
                             r.get("rank", cur["rank"]),
                             r.get("active", cur["active"]),
                             incoming_scraped, name),
                        )

                    # Assignment fields: only overwrite if incoming is newer
                    if incoming_assign > local_assign:
                        con.execute(
                            """UPDATE players SET group_name=?, agg_crimes=?, case_work=?,
                               assignments_updated_at=? WHERE username=?""",
                            (r.get("group_name", cur["group_name"]),
                             r.get("agg_crimes", cur["agg_crimes"]),
                             r.get("case_work", cur["case_work"]),
                             incoming_assign, name),
                        )

                    # Ages: always take MAX
                    new_char = max(cur["character_age"] or 0, r.get("character_age") or 0)
                    new_jail = max(cur["jail_age"] or 0, r.get("jail_age") or 0)
                    if new_char != cur["character_age"] or new_jail != cur["jail_age"]:
                        con.execute(
                            "UPDATE players SET character_age=?, jail_age=? WHERE username=?",
                            (new_char, new_jail, name),
                        )
            con.commit()
        finally:
            con.close()


def apply_synced_groups(rows: list):
    """Merge pulled group rows without re-stamping updated_at."""
    with _lock:
        con = _conn()
        try:
            for r in rows:
                name = r.get("name")
                if not name:
                    continue
                incoming_ts = r.get("updated_at") or ""
                cur = con.execute(
                    "SELECT color, type, agg_crimes, case_work, updated_at FROM groups WHERE name=?",
                    (name,),
                ).fetchone()
                if cur is None:
                    con.execute(
                        "INSERT INTO groups (name, color, type, agg_crimes, case_work, updated_at) VALUES (?,?,?,?,?,?)",
                        (name, r.get("color", "#3498db"), r.get("type", "neutral"),
                         r.get("agg_crimes", ""), r.get("case_work", ""), incoming_ts),
                    )
                elif incoming_ts > (cur["updated_at"] or ""):
                    con.execute(
                        "UPDATE groups SET color=?, type=?, agg_crimes=?, case_work=?, updated_at=? WHERE name=?",
                        (r.get("color", cur["color"]), r.get("type", cur["type"]),
                         r.get("agg_crimes", cur["agg_crimes"]),
                         r.get("case_work", cur["case_work"]),
                         incoming_ts, name),
                    )
            con.commit()
        finally:
            con.close()


def apply_synced_career(rows: list):
    """Merge career history rows — INSERT OR IGNORE by (username, ts) PK."""
    with _lock:
        con = _conn()
        try:
            for r in rows:
                con.execute(
                    """INSERT OR IGNORE INTO career_history (username, ts, rank, occupation, homecity)
                       VALUES (?,?,?,?,?)""",
                    (r.get("username", ""), r.get("ts", ""),
                     r.get("rank", ""), r.get("occupation", ""), r.get("homecity", "")),
                )
            con.commit()
        finally:
            con.close()


def get_sync_meta(key: str) -> str:
    with _lock:
        con = _conn()
        try:
            row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            return row["value"] if row else ""
        finally:
            con.close()


def set_sync_meta(key: str, value: str):
    with _lock:
        con = _conn()
        try:
            con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
            con.commit()
        finally:
            con.close()


# ---------------------------------------------------------------------------
# Permission helper — individual assignment takes precedence over group
# ---------------------------------------------------------------------------

def is_allowed(username: str, context: str, target_mode: str) -> bool:
    if target_mode == "none":
        return False
    if target_mode == "all":
        return True

    individual = get_assignment(username, context)
    if individual:
        assignment = individual
    else:
        group_name = get_player_group(username)
        assignment = get_group_assignment(group_name, context) if group_name else ""

    if target_mode == "whitelist":
        return assignment == "whitelist"
    if target_mode == "not_blacklist":
        return assignment != "blacklist"
    return True
