"""
Admin API — table viewer, user management, client registration.
All routes require admin role.
"""

from flask import Blueprint, request, jsonify

import db
import auth

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

_SYSTEM_TABLES = {"users", "clients"}
_VIEWABLE_TABLES = {
    "players", "career_history", "groups", "clients",
    "sync_log", "war_entries", "war_events", "meta", "users",
}


def _table_pk(table: str) -> str:
    pks = {
        "players": "username",
        "career_history": "id",
        "groups": "name",
        "clients": "client_id",
        "sync_log": "id",
        "war_entries": "id",
        "war_events": "id",
        "meta": "key",
        "users": "id",
    }
    return pks.get(table, "rowid")


@admin_bp.route("/tables")
@auth.admin_required
def list_tables():
    con = db.get_conn()
    try:
        tables = []
        for name in _VIEWABLE_TABLES:
            count = con.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
            tables.append({"name": name, "row_count": count})
    finally:
        con.close()
    tables.sort(key=lambda t: t["name"])
    return jsonify({"tables": tables})


@admin_bp.route("/tables/<name>")
@auth.admin_required
def view_table(name):
    if name not in _VIEWABLE_TABLES:
        return jsonify({"error": "Table not found"}), 404

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)
    per_page = min(per_page, 200)

    con = db.get_conn()
    try:
        total = con.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        cols = [r[1] for r in con.execute(f"PRAGMA table_info([{name}])").fetchall()]
        rows = db.dict_rows(con.execute(
            f"SELECT * FROM [{name}] LIMIT ? OFFSET ?",
            (per_page, (page - 1) * per_page),
        ).fetchall())
    finally:
        con.close()

    return jsonify({
        "table": name,
        "columns": cols,
        "rows": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "pk": _table_pk(name),
    })


@admin_bp.route("/tables/<name>/<pk_value>", methods=["DELETE"])
@auth.admin_required
def delete_row(name, pk_value):
    if name not in _VIEWABLE_TABLES:
        return jsonify({"error": "Table not found"}), 404

    pk = _table_pk(name)
    con = db.get_conn()
    try:
        con.execute(f"DELETE FROM [{name}] WHERE [{pk}] = ?", (pk_value,))
        con.commit()
        if con.total_changes == 0:
            return jsonify({"error": "Row not found"}), 404
    finally:
        con.close()
    return jsonify({"ok": True})


# ---- User management ----

@admin_bp.route("/users")
@auth.admin_required
def list_users():
    return jsonify({"users": auth.list_users()})


@admin_bp.route("/users", methods=["POST"])
@auth.admin_required
def create_user():
    data = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "user")
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    if role not in ("admin", "user"):
        return jsonify({"error": "role must be 'admin' or 'user'"}), 400

    user = auth.create_user(username, password, role)
    if not user:
        return jsonify({"error": "Username already exists"}), 409
    return jsonify(user), 201


@admin_bp.route("/users/<int:user_id>", methods=["PUT"])
@auth.admin_required
def update_user(user_id):
    data = request.get_json(force=True) or {}
    role = data.get("role")
    password = data.get("password")
    if role and role not in ("admin", "user"):
        return jsonify({"error": "role must be 'admin' or 'user'"}), 400
    auth.update_user(user_id, role=role, password=password)
    return jsonify({"ok": True})


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@auth.admin_required
def delete_user(user_id):
    auth.delete_user(user_id)
    return jsonify({"ok": True})


# ---- Client registration ----

@admin_bp.route("/clients", methods=["POST"])
@auth.admin_required
def register_client():
    data = request.get_json(force=True) or {}
    client_id = data.get("client_id", "").strip()
    label = data.get("label", "")
    if not client_id:
        return jsonify({"error": "client_id required"}), 400

    api_key = auth.generate_api_key()
    key_hash = auth.hash_api_key(api_key)

    con = db.get_conn()
    try:
        con.execute(
            "INSERT INTO clients (client_id, label, api_key_hash, created_at) VALUES (?, ?, ?, ?)",
            (client_id, label, key_hash, db.utcnow()),
        )
        con.commit()
    except Exception:
        return jsonify({"error": "Client ID already exists"}), 409
    finally:
        con.close()

    return jsonify({"client_id": client_id, "api_key": api_key}), 201


@admin_bp.route("/clients/<client_id>", methods=["DELETE"])
@auth.admin_required
def revoke_client(client_id):
    con = db.get_conn()
    try:
        con.execute("UPDATE clients SET active = 0 WHERE client_id = ?", (client_id,))
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True})
