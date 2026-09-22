"""
Player Hub — centralized player database management.
"""

import os

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, request, session, redirect, url_for

import db
import auth as auth_module
from sync_api import sync_bp
from crud_api import crud_bp
from war_api import war_bp
from admin_api import admin_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

app.register_blueprint(sync_bp)
app.register_blueprint(crud_bp)
app.register_blueprint(war_bp)
app.register_blueprint(admin_bp)


# ---- Page routes ----

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        user = auth_module.authenticate_user(username, password)
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("index"))
        error = "Invalid credentials"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@auth_module.login_required
def index():
    user = auth_module.get_current_user()
    return render_template("players.html", user=user)


@app.route("/player/<username>")
@auth_module.login_required
def player_detail(username):
    user = auth_module.get_current_user()
    return render_template("player_detail.html", user=user, player_name=username)


@app.route("/groups")
@auth_module.login_required
def groups_page():
    user = auth_module.get_current_user()
    return render_template("groups.html", user=user)


@app.route("/clients")
@auth_module.login_required
def clients_page():
    user = auth_module.get_current_user()
    return render_template("clients.html", user=user)


@app.route("/war")
@auth_module.login_required
def war_page():
    user = auth_module.get_current_user()
    return render_template("war.html", user=user)


@app.route("/admin/tables")
@auth_module.admin_required
def tables_page():
    user = auth_module.get_current_user()
    return render_template("admin/tables.html", user=user)


@app.route("/admin/users")
@auth_module.admin_required
def users_page():
    user = auth_module.get_current_user()
    return render_template("admin/users.html", user=user)


if __name__ == "__main__":
    db.init_db()
    auth_module.seed_admin()
    port = int(os.environ.get("HUB_PORT", 9090))
    print(f"[player_hub] Listening on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
