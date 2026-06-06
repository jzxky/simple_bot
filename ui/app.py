"""
Flask web UI for bot configuration and control.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template, request, jsonify
import config as cfg
import bot

app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
def index():
    c = cfg.load()
    return render_template("index.html", config=c)


@app.route("/save", methods=["POST"])
def save():
    data = request.get_json()
    c = cfg.load()

    c["credentials"]["email"] = data.get("email", "")
    c["credentials"]["password"] = data.get("password", "")

    c["earns"]["enabled"] = data.get("earns_enabled", False)
    c["earns"]["category"] = data.get("earn_category", "Hospital")
    c["earns"]["earn_type"] = data.get("earn_type", "surgeon")

    c["aggravated_crimes"]["enabled"] = data.get("crimes_enabled", False)
    c["aggravated_crimes"]["primary"]["crime"] = data.get("primary_crime", "pickpocket")
    c["aggravated_crimes"]["primary"]["energy_threshold"] = int(data.get("primary_threshold", 50))
    c["aggravated_crimes"]["secondary"]["crime"] = data.get("secondary_crime", "pickpocket")
    c["aggravated_crimes"]["secondary"]["energy_threshold"] = int(data.get("secondary_threshold", 50))

    c["action"]["enabled"] = data.get("action_enabled", False)
    c["action"]["type"] = data.get("action_type", "community_service")
    c["action"]["sub_option"] = data.get("action_sub", "")

    c["payback_enabled"] = data.get("payback_enabled", False)

    cfg.save(c)
    return jsonify({"ok": True})


@app.route("/start", methods=["POST"])
def start():
    bot.start()
    return jsonify({"running": True})


@app.route("/stop", methods=["POST"])
def stop():
    bot.stop()
    return jsonify({"running": False})


@app.route("/status")
def status():
    return jsonify({
        "running": bot.is_running(),
        "log": bot.state.log[-50:],
        "energy": bot.state.energy,
        "action_ready": bot.state.action_available(),
        "city": bot.state.current_city,
        "error": bot.state.last_error,
    })


def run():
    app.run(host="0.0.0.0", port=5000, debug=False)
