"""
CRUD API — UI-facing endpoints for players, groups, clients.
All routes require session auth (logged-in user).
"""

from flask import Blueprint, request, jsonify

import db
from auth import login_required, admin_required

crud_bp = Blueprint("crud", __name__, url_prefix="/api/crud")

_EDITABLE_FIELDS = {"group_name", "agg_crimes", "case_work", "alias", "notes", "monitoring"}


@crud_bp.route("/players")
@login_required
def list_players():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 100, type=int)
    per_page = min(per_page, 500)
    search = request.args.get("search", "").strip()
    sort = request.args.get("sort", "username")
    order = request.args.get("order", "asc").lower()
    active_filter = request.args.get("active")
    group_filter = request.args.get("group")
    city_filter = request.args.get("city")
    occupation_filter = request.args.get("occupation")
    rank_filter = request.args.get("rank")

    allowed_sorts = {
        "username", "homecity", "occupation", "rank", "character_age",
        "jail_age", "group_name", "scraped_at", "born_at", "died_at",
        "active", "source_client",
    }
    if sort not in allowed_sorts:
        sort = "username"
    if order not in ("asc", "desc"):
        order = "asc"

    where = []
    params = []

    if search:
        where.append("(username LIKE ? OR alias LIKE ?)")
        params.extend([f"%{search}%", f"%{search}%"])
    if active_filter is not None:
        where.append("active = ?")
        params.append(int(active_filter))
    if group_filter:
        where.append("group_name = ?")
        params.append(group_filter)
    if city_filter:
        where.append("homecity = ?")
        params.append(city_filter)
    if occupation_filter:
        where.append("occupation = ?")
        params.append(occupation_filter)
    if rank_filter:
        where.append("rank = ?")
        params.append(rank_filter)

    where_clause = " AND ".join(where) if where else "1=1"

    con = db.get_conn()
    try:
        total = con.execute(
            f"SELECT COUNT(*) FROM players WHERE {where_clause}", params
        ).fetchone()[0]

        rows = db.dict_rows(con.execute(
            f"SELECT * FROM players WHERE {where_clause} ORDER BY {sort} {order} LIMIT ? OFFSET ?",
            params + [per_page, (page - 1) * per_page],
        ).fetchall())
    finally:
        con.close()

    return jsonify({
        "players": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    })


@crud_bp.route("/players/<username>")
@login_required
def get_player(username):
    con = db.get_conn()
    try:
        player = db.dict_row(con.execute(
            "SELECT * FROM players WHERE username = ?", (username,)
        ).fetchone())
        if not player:
            return jsonify({"error": "Player not found"}), 404

        career = db.dict_rows(con.execute(
            "SELECT ts, rank, occupation, homecity FROM career_history WHERE username = ? ORDER BY id DESC",
            (username,),
        ).fetchall())
    finally:
        con.close()

    player["career_history"] = career
    return jsonify(player)


@crud_bp.route("/players/<username>", methods=["PUT"])
@login_required
def update_player(username):
    data = request.get_json(force=True) or {}
    updates = {k: v for k, v in data.items() if k in _EDITABLE_FIELDS}
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400

    sets = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [db.utcnow(), username]

    con = db.get_conn()
    try:
        con.execute(
            f"UPDATE players SET {sets}, assignments_updated_at=? WHERE username=?",
            vals,
        )
        con.commit()
        if con.total_changes == 0:
            return jsonify({"error": "Player not found"}), 404
    finally:
        con.close()
    return jsonify({"ok": True})


@crud_bp.route("/players/<username>", methods=["DELETE"])
@admin_required
def delete_player(username):
    con = db.get_conn()
    try:
        con.execute("DELETE FROM players WHERE username = ?", (username,))
        con.execute("DELETE FROM career_history WHERE username = ?", (username,))
        con.commit()
        if con.total_changes == 0:
            return jsonify({"error": "Player not found"}), 404
    finally:
        con.close()
    return jsonify({"ok": True})


# ---- Groups ----

@crud_bp.route("/groups")
@login_required
def list_groups():
    con = db.get_conn()
    try:
        groups = db.dict_rows(con.execute(
            """SELECT g.name, g.color, g.type, g.agg_crimes, g.case_work, g.updated_at,
                      COUNT(p.username) as member_count
               FROM groups g
               LEFT JOIN players p ON p.group_name = g.name AND p.active = 1
               GROUP BY g.name
               ORDER BY g.name"""
        ).fetchall())
    finally:
        con.close()
    return jsonify({"groups": groups})


@crud_bp.route("/groups", methods=["POST"])
@login_required
def create_group():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Name required"}), 400

    con = db.get_conn()
    try:
        con.execute(
            "INSERT INTO groups (name, color, type, updated_at) VALUES (?, ?, ?, ?)",
            (name, data.get("color", "#3498db"), data.get("type", "neutral"), db.utcnow()),
        )
        con.commit()
    except Exception:
        return jsonify({"error": "Group already exists"}), 409
    finally:
        con.close()
    return jsonify({"ok": True}), 201


@crud_bp.route("/groups/<name>", methods=["PUT"])
@login_required
def update_group(name):
    data = request.get_json(force=True) or {}
    allowed = {"color", "type", "agg_crimes", "case_work"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"error": "No valid fields"}), 400

    sets = ", ".join(f"{k}=?" for k in updates)
    vals = list(updates.values()) + [db.utcnow(), name]

    con = db.get_conn()
    try:
        con.execute(f"UPDATE groups SET {sets}, updated_at=? WHERE name=?", vals)
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@crud_bp.route("/groups/<name>/rename", methods=["POST"])
@login_required
def rename_group(name):
    data = request.get_json(force=True) or {}
    new_name = data.get("new_name", "").strip()
    if not new_name:
        return jsonify({"error": "new_name required"}), 400

    con = db.get_conn()
    try:
        existing = con.execute("SELECT 1 FROM groups WHERE name = ?", (new_name,)).fetchone()
        if existing:
            return jsonify({"error": "Target name already exists"}), 409
        con.execute("UPDATE groups SET name = ?, updated_at = ? WHERE name = ?", (new_name, db.utcnow(), name))
        con.execute("UPDATE players SET group_name = ?, assignments_updated_at = ? WHERE group_name = ?",
                     (new_name, db.utcnow(), name))
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@crud_bp.route("/groups/<name>", methods=["DELETE"])
@admin_required
def delete_group(name):
    con = db.get_conn()
    try:
        con.execute("UPDATE players SET group_name = '', assignments_updated_at = ? WHERE group_name = ?",
                     (db.utcnow(), name))
        con.execute("DELETE FROM groups WHERE name = ?", (name,))
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


@crud_bp.route("/groups/<name>/members")
@login_required
def group_members(name):
    con = db.get_conn()
    try:
        members = db.dict_rows(con.execute(
            "SELECT username, occupation, rank, homecity, active FROM players WHERE group_name = ? ORDER BY username",
            (name,),
        ).fetchall())
    finally:
        con.close()
    return jsonify({"members": members})


# ---- Clients ----

@crud_bp.route("/clients")
@login_required
def list_clients():
    con = db.get_conn()
    try:
        clients = db.dict_rows(con.execute(
            "SELECT client_id, label, last_push_at, last_pull_at, player_count, created_at, active FROM clients ORDER BY client_id"
        ).fetchall())
    finally:
        con.close()
    return jsonify({"clients": clients})


@crud_bp.route("/clients/<client_id>", methods=["PUT"])
@login_required
def update_client(client_id):
    data = request.get_json(force=True) or {}
    label = data.get("label")
    if label is None:
        return jsonify({"error": "label required"}), 400
    con = db.get_conn()
    try:
        con.execute("UPDATE clients SET label = ? WHERE client_id = ?", (label, client_id))
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})


# ---- Sync log ----

@crud_bp.route("/sync_log")
@login_required
def sync_log():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    con = db.get_conn()
    try:
        total = con.execute("SELECT COUNT(*) FROM sync_log").fetchone()[0]
        rows = db.dict_rows(con.execute(
            "SELECT * FROM sync_log ORDER BY id DESC LIMIT ? OFFSET ?",
            (per_page, (page - 1) * per_page),
        ).fetchall())
    finally:
        con.close()
    return jsonify({"log": rows, "total": total, "page": page, "per_page": per_page})


# ---- Filter options ----

@crud_bp.route("/filter_options")
@login_required
def filter_options():
    con = db.get_conn()
    try:
        cities = [r[0] for r in con.execute("SELECT DISTINCT homecity FROM players WHERE homecity != '' ORDER BY homecity").fetchall()]
        occupations = [r[0] for r in con.execute("SELECT DISTINCT occupation FROM players WHERE occupation != '' ORDER BY occupation").fetchall()]
        ranks = [r[0] for r in con.execute("SELECT DISTINCT rank FROM players WHERE rank != '' ORDER BY rank").fetchall()]
        groups = [r[0] for r in con.execute("SELECT name FROM groups ORDER BY name").fetchall()]
    finally:
        con.close()
    return jsonify({"cities": cities, "occupations": occupations, "ranks": ranks, "groups": groups})
