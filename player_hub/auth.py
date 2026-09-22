"""
Authentication — user accounts with bcrypt, API key auth for bot clients.
"""

import functools
import hashlib
import os
import secrets

import bcrypt
from flask import session, request, redirect, url_for, jsonify

import db


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    return secrets.token_urlsafe(32)


def seed_admin():
    """Create default admin from env vars if no users exist."""
    con = db.get_conn()
    try:
        count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if count > 0:
            return
        username = os.environ.get("ADMIN_USER", "admin")
        password = os.environ.get("ADMIN_PASS", "changeme")
        con.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, 'admin', ?)",
            (username, hash_password(password), db.utcnow()),
        )
        con.commit()
    finally:
        con.close()


def authenticate_user(username: str, password: str) -> dict | None:
    con = db.get_conn()
    try:
        row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row and check_password(password, row["password_hash"]):
            con.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?",
                (db.utcnow(), row["id"]),
            )
            con.commit()
            return db.dict_row(row)
        return None
    finally:
        con.close()


def get_current_user() -> dict | None:
    uid = session.get("user_id")
    if not uid:
        return None
    con = db.get_conn()
    try:
        row = con.execute("SELECT id, username, role FROM users WHERE id = ?", (uid,)).fetchone()
        return db.dict_row(row)
    finally:
        con.close()


def login_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            if request.is_json or request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        user = get_current_user()
        if not user or user["role"] != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return f(*args, **kwargs)
    return wrapper


def require_api_key(f):
    """Authenticate bot clients via Bearer token."""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "API key required"}), 401
        key = auth[7:]
        key_hash = hash_api_key(key)
        con = db.get_conn()
        try:
            row = con.execute(
                "SELECT client_id FROM clients WHERE api_key_hash = ? AND active = 1",
                (key_hash,),
            ).fetchone()
            if not row:
                return jsonify({"error": "Invalid or revoked API key"}), 401
            request.client_id = row["client_id"]
        finally:
            con.close()
        return f(*args, **kwargs)
    return wrapper


# ---- User CRUD (admin) ----

def list_users() -> list:
    con = db.get_conn()
    try:
        rows = con.execute(
            "SELECT id, username, role, created_at, last_login_at FROM users ORDER BY id"
        ).fetchall()
        return db.dict_rows(rows)
    finally:
        con.close()


def create_user(username: str, password: str, role: str = "user") -> dict | None:
    con = db.get_conn()
    try:
        con.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, db.utcnow()),
        )
        con.commit()
        row = con.execute("SELECT id, username, role, created_at FROM users WHERE username = ?", (username,)).fetchone()
        return db.dict_row(row)
    except Exception:
        return None
    finally:
        con.close()


def update_user(user_id: int, role: str = None, password: str = None) -> bool:
    con = db.get_conn()
    try:
        if role:
            con.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if password:
            con.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(password), user_id))
        con.commit()
        return con.total_changes > 0
    finally:
        con.close()


def delete_user(user_id: int) -> bool:
    con = db.get_conn()
    try:
        con.execute("DELETE FROM users WHERE id = ?", (user_id,))
        con.commit()
        return con.total_changes > 0
    finally:
        con.close()
