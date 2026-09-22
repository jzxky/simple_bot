"""
Sync API — bot-facing endpoints that replace sync_server.py.
All routes require API key auth via Authorization: Bearer <key>.
"""

from datetime import datetime, timezone

from flask import Blueprint, request, jsonify

import db
from auth import require_api_key

sync_bp = Blueprint("sync", __name__, url_prefix="/api/sync")

_EPOCH = "1970-01-01T00:00:00Z"

_PLAYER_EXTRA_FIELDS = [
    "pic_url", "sex", "wealth", "scripting", "godfather",
    "crew_name", "capos", "alias", "notes", "monitoring",
    "born_at", "died_at", "respect", "respect_last_checked",
]


def _upsert_players(con, rows: list, client_id: str):
    for r in rows:
        name = r.get("username")
        if not name:
            continue
        incoming_scraped = r.get("scraped_at") or ""
        incoming_assign = r.get("assignments_updated_at") or ""
        cur = con.execute(
            """SELECT character_age, jail_age, scraped_at, assignments_updated_at
               FROM players WHERE username=?""",
            (name,),
        ).fetchone()

        if cur is None:
            con.execute(
                """INSERT INTO players
                   (username, homecity, occupation, rank, active,
                    group_name, agg_crimes, case_work,
                    character_age, jail_age,
                    assignments_updated_at, scraped_at,
                    pic_url, sex, wealth, scripting, godfather,
                    crew_name, capos, alias, notes, monitoring,
                    born_at, died_at, respect, respect_last_checked,
                    source_client)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (name,
                 r.get("homecity", ""), r.get("occupation", ""),
                 r.get("rank", ""), r.get("active", 1),
                 r.get("group_name", ""), r.get("agg_crimes", ""),
                 r.get("case_work", ""),
                 r.get("character_age", 0), r.get("jail_age", 0),
                 incoming_assign, incoming_scraped,
                 r.get("pic_url", ""), r.get("sex", ""),
                 r.get("wealth", ""), r.get("scripting", ""),
                 r.get("godfather", ""),
                 r.get("crew_name", ""), r.get("capos", ""),
                 r.get("alias", ""), r.get("notes", ""),
                 r.get("monitoring", 0),
                 r.get("born_at", ""), r.get("died_at", ""),
                 r.get("respect", ""), r.get("respect_last_checked", 0),
                 client_id),
            )
        else:
            local_scraped = cur["scraped_at"] or ""
            local_assign = cur["assignments_updated_at"] or ""

            if incoming_scraped > local_scraped:
                sets = ["homecity=?", "occupation=?", "rank=?", "active=?",
                        "scraped_at=?", "source_client=?"]
                vals = [r.get("homecity", ""), r.get("occupation", ""),
                        r.get("rank", ""), r.get("active", 1),
                        incoming_scraped, client_id]
                for field in _PLAYER_EXTRA_FIELDS:
                    if field in r:
                        sets.append(f"{field}=?")
                        vals.append(r[field])
                vals.append(name)
                con.execute(
                    f"UPDATE players SET {', '.join(sets)} WHERE username=?",
                    vals,
                )

            if incoming_assign > local_assign:
                con.execute(
                    """UPDATE players SET group_name=?, agg_crimes=?, case_work=?,
                       assignments_updated_at=?, source_client=? WHERE username=?""",
                    (r.get("group_name", ""), r.get("agg_crimes", ""),
                     r.get("case_work", ""),
                     incoming_assign, client_id, name),
                )

            incoming_char = r.get("character_age") or 0
            incoming_jail = r.get("jail_age") or 0
            cur_char = cur["character_age"] or 0
            cur_jail = cur["jail_age"] or 0
            if incoming_char > cur_char or incoming_jail > cur_jail:
                con.execute(
                    "UPDATE players SET character_age=?, jail_age=? WHERE username=?",
                    (max(cur_char, incoming_char), max(cur_jail, incoming_jail), name),
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
        if not uname:
            continue
        rank = r.get("rank", "")
        occ = r.get("occupation", "")
        city = r.get("homecity", "")
        last = con.execute(
            "SELECT rank, occupation, homecity FROM career_history WHERE username=? ORDER BY id DESC LIMIT 1",
            (uname,),
        ).fetchone()
        if last and last["rank"] == rank and last["occupation"] == occ and last["homecity"] == city:
            continue
        con.execute(
            "INSERT OR IGNORE INTO career_history (username, ts, rank, occupation, homecity) VALUES (?,?,?,?,?)",
            (uname, r.get("ts", ""), rank, occ, city),
        )


def _log_sync(con, client_id: str, action: str, players: int, groups: int, career: int):
    con.execute(
        "INSERT INTO sync_log (ts, client_id, action, player_count, group_count, career_count) VALUES (?,?,?,?,?,?)",
        (db.utcnow(), client_id, action, players, groups, career),
    )


@sync_bp.route("/health")
def health():
    con = db.get_conn()
    try:
        count = con.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    finally:
        con.close()
    return jsonify({"ok": True, "player_count": count})


@sync_bp.route("/push", methods=["POST"])
@require_api_key
def push():
    data = request.get_json(force=True) or {}
    client_id = request.client_id
    players = data.get("players", [])
    groups = data.get("groups", [])
    career = data.get("career", [])

    con = db.get_conn()
    try:
        _upsert_players(con, players, client_id)
        _upsert_groups(con, groups)
        _upsert_career(con, career)
        _log_sync(con, client_id, "push", len(players), len(groups), len(career))
        con.execute(
            """INSERT INTO clients (client_id, api_key_hash, last_push_at, player_count, created_at)
               VALUES (?, '', ?, ?, ?)
               ON CONFLICT(client_id) DO UPDATE SET
                   last_push_at=excluded.last_push_at,
                   player_count=excluded.player_count""",
            (client_id, db.utcnow(), len(players), db.utcnow()),
        )
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True, "server_time": db.utcnow()})


@sync_bp.route("/pull")
@require_api_key
def pull():
    since = request.args.get("since") or _EPOCH
    client_id = request.client_id
    con = db.get_conn()
    try:
        players = db.dict_rows(con.execute(
            """SELECT username, homecity, occupation, rank, active,
                      group_name, agg_crimes, case_work,
                      character_age, jail_age,
                      assignments_updated_at, scraped_at,
                      pic_url, sex, wealth, scripting, godfather,
                      crew_name, capos, alias, notes, monitoring,
                      born_at, died_at, respect, respect_last_checked
               FROM players
               WHERE COALESCE(assignments_updated_at,'') > ?
                  OR COALESCE(scraped_at,'') > ?""",
            (since, since),
        ).fetchall())
        groups = db.dict_rows(con.execute(
            "SELECT name, color, type, agg_crimes, case_work, updated_at FROM groups WHERE COALESCE(updated_at,'') > ?",
            (since,),
        ).fetchall())
        career = db.dict_rows(con.execute(
            "SELECT username, ts, rank, occupation, homecity FROM career_history WHERE ts > ?",
            (since,),
        ).fetchall())
        _log_sync(con, client_id, "pull", len(players), len(groups), len(career))
        con.execute(
            """UPDATE clients SET last_pull_at = ? WHERE client_id = ?""",
            (db.utcnow(), client_id),
        )
        con.commit()
    finally:
        con.close()
    return jsonify({
        "players": players,
        "groups": groups,
        "career": career,
        "server_time": db.utcnow(),
    })


@sync_bp.route("/groups/full")
@require_api_key
def groups_full():
    con = db.get_conn()
    try:
        groups = db.dict_rows(con.execute(
            "SELECT name, color, type, agg_crimes, case_work, updated_at FROM groups"
        ).fetchall())
    finally:
        con.close()
    return jsonify({"groups": groups, "server_time": db.utcnow()})
