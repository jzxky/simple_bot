"""
player_db.py — SQLite-backed player store.

Tables:
  players        — current state per player
  career_history — append-only change log (one row per state change)
  groups         — group definitions
  meta           — key/value (e.g. last_updated)
"""

import os
import json
import sqlite3
import threading
from datetime import datetime

import paths

DB_PATH = os.path.join(paths.data_dir(), "players.db")
_DEAD_CITIES = {"heaven", "hell", "locked"}

_lock = threading.Lock()

# Tags computed from career_history occupations (including current).
# requires_all — every listed occupation must appear at some point.
# requires_any — at least one listed occupation must appear at some point.
CAREER_TAGS = [
    {"tag": "CM3", "requires_all": {"Fire Chief", "Hospital Director"}},
    {"tag": "TX",  "requires_any": {"Commissioner-General"}},
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    username   TEXT PRIMARY KEY,
    homecity   TEXT DEFAULT '',
    occupation TEXT DEFAULT '',
    rank       TEXT DEFAULT '',
    active     INTEGER DEFAULT 1,
    group_name TEXT DEFAULT '',
    agg_crimes TEXT DEFAULT '',
    case_work  TEXT DEFAULT ''
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
    name  TEXT PRIMARY KEY,
    color TEXT DEFAULT '#888888'
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX IF NOT EXISTS idx_career_username ON career_history(username);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    """Create schema. Migrate from players.json if DB is empty."""
    with _lock:
        con = _conn()
        try:
            con.executescript(_SCHEMA)
            con.commit()
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
            (g["name"], g.get("color", "#888888")),
        )

    lists = store.get("lists", {})
    agg_map = lists.get("agg_crimes", {})
    cw_map  = lists.get("case_work", {})
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for name, p in store.get("players", {}).items():
        active = 1 if p.get("active", True) else 0
        homecity   = p.get("homecity", "")
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
                          group_name, agg_crimes, case_work
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
            return [dict(r) for r in
                    con.execute("SELECT name, color FROM groups ORDER BY name").fetchall()]
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


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def upsert_players(player_list: list):
    """Update player records. Appends career_history when rank/occupation/homecity changes."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _lock:
        con = _conn()
        try:
            for p in player_list:
                name       = p["username"]
                homecity   = p.get("homecity", "")
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
                    """INSERT INTO players (username, homecity, occupation, rank, active)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(username) DO UPDATE SET
                           homecity=excluded.homecity,
                           occupation=excluded.occupation,
                           rank=excluded.rank,
                           active=excluded.active""",
                    (name, homecity, occupation, rank, active),
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
    """Mark players absent from a refresh as inactive only when their city is a dead city."""
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


def set_assignment(username: str, context: str, value: str):
    col = "agg_crimes" if context == "agg_crimes" else "case_work"
    with _lock:
        con = _conn()
        try:
            con.execute(f"UPDATE players SET {col}=? WHERE username=?", (value, username))
            con.commit()
        finally:
            con.close()


def set_player_group(username: str, group_name: str):
    with _lock:
        con = _conn()
        try:
            con.execute("UPDATE players SET group_name=? WHERE username=?", (group_name, username))
            con.commit()
        finally:
            con.close()


def create_group(name: str, color: str) -> bool:
    with _lock:
        con = _conn()
        try:
            try:
                con.execute("INSERT INTO groups (name, color) VALUES (?, ?)", (name, color or "#888888"))
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
    with _lock:
        con = _conn()
        try:
            con.execute("UPDATE groups SET color=? WHERE name=?", (color, name))
            con.commit()
        finally:
            con.close()


# ---------------------------------------------------------------------------
# Permission helper (used by bot / executor)
# ---------------------------------------------------------------------------

def is_allowed(username: str, context: str, target_mode: str) -> bool:
    if target_mode == "none":
        return False
    if target_mode == "all":
        return True
    assignment = get_assignment(username, context)
    if target_mode == "whitelist":
        return assignment == "whitelist"
    if target_mode == "not_blacklist":
        return assignment != "blacklist"
    return True
