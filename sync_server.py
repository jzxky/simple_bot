"""
sync_server.py — Standalone player-list sync server.

Run on any always-on device accessible to all bot instances:
    python sync_server.py [--host 0.0.0.0] [--port 9090] [--db /path/to/sync_server.db]

All bot clients point their sync.server_url at this server.

Conflict resolution:
  character_age / jail_age    — MAX(existing, incoming) — never decrease
  homecity/occupation/rank    — last-write-wins on scraped_at
  agg_crimes/case_work/group  — last-write-wins on assignments_updated_at
  career_history              — INSERT OR IGNORE by (username, ts)
  groups                      — last-write-wins on updated_at
"""

import argparse
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone

from flask import Flask, request, jsonify

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_DB_PATH = os.path.join(os.path.dirname(__file__), "sync_server.db")
_lock = threading.Lock()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    username               TEXT PRIMARY KEY,
    homecity               TEXT DEFAULT '',
    occupation             TEXT DEFAULT '',
    rank                   TEXT DEFAULT '',
    active                 INTEGER DEFAULT 1,
    group_name             TEXT DEFAULT '',
    agg_crimes             TEXT DEFAULT '',
    case_work              TEXT DEFAULT '',
    character_age          INTEGER DEFAULT 0,
    jail_age               INTEGER DEFAULT 0,
    last_age_tick_at       TEXT DEFAULT '',
    assignments_updated_at TEXT DEFAULT '',
    scraped_at             TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS groups (
    name       TEXT PRIMARY KEY,
    color      TEXT DEFAULT '#3498db',
    type       TEXT DEFAULT 'neutral',
    agg_crimes TEXT DEFAULT '',
    case_work  TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS career (
    username   TEXT NOT NULL,
    ts         TEXT NOT NULL,
    rank       TEXT DEFAULT '',
    occupation TEXT DEFAULT '',
    homecity   TEXT DEFAULT '',
    PRIMARY KEY (username, ts)
);
"""

_EPOCH = "1970-01-01T00:00:00Z"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with _lock:
        con = _conn()
        try:
            con.executescript(_SCHEMA)
            con.commit()
            _migrate_career_ts_format(con)
            _migrate_add_last_age_tick(con)
        finally:
            con.close()


def _migrate_add_last_age_tick(con):
    cols = [r[1] for r in con.execute("PRAGMA table_info(players)").fetchall()]
    if "last_age_tick_at" not in cols:
        con.execute("ALTER TABLE players ADD COLUMN last_age_tick_at TEXT DEFAULT ''")
        con.commit()


def _migrate_career_ts_format(con):
    """Convert old local-time career timestamps to UTC ISO format."""
    rows = con.execute(
        "SELECT username, ts, rank, occupation, homecity FROM career WHERE ts LIKE '____-__-__ __:__:__'"
    ).fetchall()
    if not rows:
        return
    for row in rows:
        old_ts = row[1]
        new_ts = old_ts[:10] + "T" + old_ts[11:] + "Z"
        con.execute(
            "UPDATE career SET ts = ? WHERE username = ? AND ts = ?",
            (new_ts, row[0], old_ts),
        )
    con.commit()


def _upsert_players(con, rows: list):
    for r in rows:
        name = r.get("username")
        if not name:
            continue
        incoming_scraped = r.get("scraped_at") or ""
        incoming_assign  = r.get("assignments_updated_at") or ""
        cur = con.execute(
            """SELECT character_age, jail_age, last_age_tick_at, scraped_at, assignments_updated_at
               FROM players WHERE username=?""", (name,)
        ).fetchone()

        if cur is None:
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

            if incoming_scraped > local_scraped:
                con.execute(
                    """UPDATE players SET homecity=?, occupation=?, rank=?, active=?,
                       scraped_at=? WHERE username=?""",
                    (r.get("homecity", ""), r.get("occupation", ""),
                     r.get("rank", ""), r.get("active", 1),
                     incoming_scraped, name),
                )

            if incoming_assign > local_assign:
                con.execute(
                    """UPDATE players SET group_name=?, agg_crimes=?, case_work=?,
                       assignments_updated_at=? WHERE username=?""",
                    (r.get("group_name", ""), r.get("agg_crimes", ""),
                     r.get("case_work", ""),
                     incoming_assign, name),
                )

            # Ages: take MAX, but only accept increases if >=30 min since last tick
            incoming_char = r.get("character_age") or 0
            incoming_jail = r.get("jail_age") or 0
            cur_char = cur["character_age"] or 0
            cur_jail = cur["jail_age"] or 0
            if incoming_char > cur_char or incoming_jail > cur_jail:
                last_tick = cur["last_age_tick_at"] or ""
                now = _utcnow()
                accept = True
                if last_tick:
                    try:
                        prev = datetime.strptime(last_tick, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        curr = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        accept = (curr - prev).total_seconds() >= 1500  # 25 min buffer
                    except ValueError:
                        pass
                if accept:
                    con.execute(
                        "UPDATE players SET character_age=?, jail_age=?, last_age_tick_at=? WHERE username=?",
                        (max(cur_char, incoming_char), max(cur_jail, incoming_jail), now, name),
                    )


def _upsert_groups(con, rows: list):
    for r in rows:
        name = r.get("name")
        if not name:
            continue
        incoming_ts = r.get("updated_at") or ""
        cur = con.execute("SELECT updated_at FROM groups WHERE name=?", (name,)).fetchone()
        if cur is None:
            con.execute(
                "INSERT INTO groups (name, color, type, agg_crimes, case_work, updated_at) VALUES (?,?,?,?,?,?)",
                (name, r.get("color", "#3498db"), r.get("type", "neutral"),
                 r.get("agg_crimes", ""), r.get("case_work", ""), incoming_ts),
            )
        elif incoming_ts > (cur["updated_at"] or ""):
            con.execute(
                "UPDATE groups SET color=?, type=?, agg_crimes=?, case_work=?, updated_at=? WHERE name=?",
                (r.get("color", "#3498db"), r.get("type", "neutral"),
                 r.get("agg_crimes", ""), r.get("case_work", ""),
                 incoming_ts, name),
            )


def _upsert_career(con, rows: list):
    for r in rows:
        uname = r.get("username", "")
        rank = r.get("rank", "")
        occ = r.get("occupation", "")
        city = r.get("homecity", "")
        if not uname:
            continue
        last = con.execute(
            "SELECT rank, occupation, homecity FROM career WHERE username=? ORDER BY ts DESC LIMIT 1",
            (uname,),
        ).fetchone()
        if last and last["rank"] == rank and last["occupation"] == occ and last["homecity"] == city:
            continue
        con.execute(
            """INSERT OR IGNORE INTO career (username, ts, rank, occupation, homecity)
               VALUES (?,?,?,?,?)""",
            (uname, r.get("ts", ""), rank, occ, city),
        )


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)


@app.route("/sync/health")
def health():
    with _lock:
        con = _conn()
        try:
            count = con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        finally:
            con.close()
    return jsonify({"ok": True, "player_count": count})


@app.route("/sync/push", methods=["POST"])
def push():
    data = request.get_json(force=True) or {}
    with _lock:
        con = _conn()
        try:
            _upsert_players(con, data.get("players", []))
            _upsert_groups(con, data.get("groups", []))
            _upsert_career(con, data.get("career", []))
            con.commit()
        finally:
            con.close()
    return jsonify({"ok": True, "server_time": _utcnow()})


@app.route("/sync/groups/full")
def groups_full():
    """Return all groups on the server (for full reconciliation on connect)."""
    with _lock:
        con = _conn()
        try:
            groups = [dict(r) for r in con.execute(
                "SELECT name, color, type, agg_crimes, case_work, updated_at FROM groups"
            ).fetchall()]
        finally:
            con.close()
    return jsonify({"groups": groups, "server_time": _utcnow()})


@app.route("/sync/pull")
def pull():
    since = request.args.get("since") or _EPOCH
    with _lock:
        con = _conn()
        try:
            players = [dict(r) for r in con.execute(
                """SELECT username, homecity, occupation, rank, active,
                          group_name, agg_crimes, case_work,
                          character_age, jail_age,
                          assignments_updated_at, scraped_at
                   FROM players
                   WHERE COALESCE(assignments_updated_at,'') > ?
                      OR COALESCE(scraped_at,'') > ?""",
                (since, since),
            ).fetchall()]
            groups = [dict(r) for r in con.execute(
                "SELECT name, color, type, agg_crimes, case_work, updated_at FROM groups WHERE COALESCE(updated_at,'') > ?",
                (since,),
            ).fetchall()]
            career = [dict(r) for r in con.execute(
                "SELECT username, ts, rank, occupation, homecity FROM career WHERE ts > ?",
                (since,),
            ).fetchall()]
        finally:
            con.close()
    return jsonify({
        "players": players,
        "groups": groups,
        "career": career,
        "server_time": _utcnow(),
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="simple_bot player sync server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9090)
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    if args.db:
        _DB_PATH = args.db

    init_db()
    print(f"[sync_server] Listening on {args.host}:{args.port}, db={_DB_PATH}")
    app.run(host=args.host, port=args.port, threaded=True)
