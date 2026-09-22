"""
War Mode API — centralized war tracking.
UI-facing endpoints use session auth, bot-facing endpoints use API key auth.
"""

from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify

import db
from auth import login_required, require_api_key

war_bp = Blueprint("war", __name__)

SIDES = ("opps", "friendlies")
WHACK_TYPES = ("Normal", "Bodyguard")
_OPEN_OFFSET = {"Normal": 3 * 60 + 40, "Bodyguard": 3 * 60}
_WINDOW_LEN = {"Normal": 40, "Bodyguard": 0}
_TS_FMT = "%Y-%m-%d %H:%M:%S"
_MAX_EVENTS = 200


def _compute_status(entry: dict) -> dict:
    """Compute Open/Protected/In-Window status for a war entry."""
    wt = entry.get("whack_type", "Normal")
    lwt = entry.get("last_whack_time", "")
    if not lwt:
        entry["status"] = "Open"
        entry["window_open"] = ""
        entry["window_close"] = ""
        return entry

    try:
        last_whack = datetime.strptime(lwt, _TS_FMT)
    except ValueError:
        entry["status"] = "Open"
        entry["window_open"] = ""
        entry["window_close"] = ""
        return entry

    open_at = last_whack + timedelta(minutes=_OPEN_OFFSET.get(wt, 220))
    close_at = open_at + timedelta(minutes=_WINDOW_LEN.get(wt, 40))
    now = datetime.now()

    if now < open_at:
        entry["status"] = "Protected"
    elif now <= close_at:
        entry["status"] = "In-Window"
    else:
        entry["status"] = "Open"

    entry["window_open"] = open_at.strftime(_TS_FMT)
    entry["window_close"] = close_at.strftime(_TS_FMT)
    return entry


def _get_war_state() -> dict:
    con = db.get_conn()
    try:
        opps = db.dict_rows(con.execute(
            "SELECT * FROM war_entries WHERE side='opps' ORDER BY name"
        ).fetchall())
        friendlies = db.dict_rows(con.execute(
            "SELECT * FROM war_entries WHERE side='friendlies' ORDER BY name"
        ).fetchall())
        events = db.dict_rows(con.execute(
            "SELECT * FROM war_events ORDER BY id DESC LIMIT ?", (_MAX_EVENTS,)
        ).fetchall())
    finally:
        con.close()

    for e in opps:
        _compute_status(e)
    for e in friendlies:
        _compute_status(e)

    return {"opps": opps, "friendlies": friendlies, "events": events}


def _add_event(con, message: str, source_client: str = ""):
    con.execute(
        "INSERT INTO war_events (ts, message, source_client) VALUES (?, ?, ?)",
        (db.utcnow(), message, source_client),
    )
    count = con.execute("SELECT COUNT(*) FROM war_events").fetchone()[0]
    if count > _MAX_EVENTS:
        con.execute(
            "DELETE FROM war_events WHERE id IN (SELECT id FROM war_events ORDER BY id ASC LIMIT ?)",
            (count - _MAX_EVENTS,),
        )


# ---- UI-facing endpoints ----

@war_bp.route("/api/crud/war/state")
@login_required
def war_state():
    return jsonify(_get_war_state())


@war_bp.route("/api/crud/war/add", methods=["POST"])
@login_required
def war_add():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    side = data.get("side", "")
    if not name or side not in SIDES:
        return jsonify({"error": "name and valid side required"}), 400

    con = db.get_conn()
    try:
        con.execute(
            """INSERT OR IGNORE INTO war_entries (name, side, updated_at, source_client)
               VALUES (?, ?, ?, ?)""",
            (name, side, db.utcnow(), "ui"),
        )
        _add_event(con, f"Added {name} to {side}", "ui")
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@war_bp.route("/api/crud/war/remove", methods=["POST"])
@login_required
def war_remove():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    side = data.get("side", "")
    if not name or side not in SIDES:
        return jsonify({"error": "name and valid side required"}), 400

    con = db.get_conn()
    try:
        con.execute("DELETE FROM war_entries WHERE name = ? AND side = ?", (name, side))
        _add_event(con, f"Removed {name} from {side}", "ui")
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@war_bp.route("/api/crud/war/update", methods=["POST"])
@login_required
def war_update():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    side = data.get("side", "")
    if not name or side not in SIDES:
        return jsonify({"error": "name and valid side required"}), 400

    sets = []
    vals = []
    for field in ("ws", "whack_type", "last_whack_time"):
        if field in data:
            sets.append(f"{field}=?")
            vals.append(data[field])

    if not sets:
        return jsonify({"error": "No fields to update"}), 400

    sets.append("updated_at=?")
    vals.append(db.utcnow())
    sets.append("source_client=?")
    vals.append("ui")
    vals.extend([name, side])

    con = db.get_conn()
    try:
        con.execute(
            f"UPDATE war_entries SET {', '.join(sets)} WHERE name=? AND side=?",
            vals,
        )
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@war_bp.route("/api/crud/war/clear_events", methods=["POST"])
@login_required
def war_clear_events():
    con = db.get_conn()
    try:
        con.execute("DELETE FROM war_events")
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


# ---- Bot-facing endpoints ----

@war_bp.route("/api/sync/war/lists")
@require_api_key
def war_lists():
    state = _get_war_state()
    return jsonify({"opps": state["opps"], "friendlies": state["friendlies"]})


@war_bp.route("/api/sync/war/record_ws", methods=["POST"])
@require_api_key
def war_record_ws():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    ws = data.get("ws")
    if not name or ws is None:
        return jsonify({"error": "name and ws required"}), 400

    client_id = request.client_id
    con = db.get_conn()
    try:
        row = con.execute(
            "SELECT ws, side FROM war_entries WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return jsonify({"error": "Name not in war list"}), 404
        if ws > row["ws"]:
            con.execute(
                "UPDATE war_entries SET ws=?, updated_at=?, source_client=? WHERE name=?",
                (ws, db.utcnow(), client_id, name),
            )
            _add_event(con, f"{name} WS {row['ws']} → {ws} (detected by {client_id})", client_id)
            con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@war_bp.route("/api/sync/war/check_update", methods=["POST"])
@require_api_key
def war_check_update():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400

    client_id = request.client_id
    con = db.get_conn()
    try:
        con.execute(
            "UPDATE war_entries SET last_checked=?, source_client=? WHERE name=?",
            (db.utcnow(), client_id, name),
        )
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})
