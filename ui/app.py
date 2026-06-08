"""
Flask web UI for bot configuration and control.
"""

import sys
import os
import base64
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template, request, jsonify, abort
import config as cfg
import bot
import paths

_ui_root = os.path.join(paths.resource_dir(), "ui")
app = Flask(__name__,
            template_folder=os.path.join(_ui_root, "templates"),
            static_folder=os.path.join(_ui_root, "static"))


@app.route("/")
def index():
    c = cfg.load()
    return render_template("index.html", config=c)


@app.route("/save", methods=["POST"])
def save():
    data = request.get_json()
    c = cfg.load()

    cfg.save_env(data.get("email", ""), data.get("password", ""))

    c["earns"]["enabled"] = data.get("earns_enabled", False)
    c["earns"]["category"] = data.get("earn_category", "Hospital")
    c["earns"]["earn_type"] = data.get("earn_type", "surgeon")

    c["aggravated_crimes"]["enabled"] = data.get("crimes_enabled", False)
    c["aggravated_crimes"]["primary"]["crime"] = data.get("primary_crime", "pickpocket")
    c["aggravated_crimes"]["primary"]["energy_threshold"] = int(data.get("primary_threshold", 50))
    c["aggravated_crimes"].setdefault("away_crime", {})
    c["aggravated_crimes"]["away_crime"]["crime"] = data.get("away_crime", "pickpocket")
    c["aggravated_crimes"]["away_crime"]["energy_threshold"] = int(data.get("away_threshold", 50))
    c["aggravated_crimes"].setdefault("armed", {})
    c["aggravated_crimes"]["armed"]["agg_private"] = data.get("armed_agg_private", False)
    c["aggravated_crimes"]["armed"]["agg_drug_house"] = data.get("armed_agg_drug_house", False)
    c["aggravated_crimes"]["armed"]["payback_private"] = data.get("armed_payback_private", False)
    c["aggravated_crimes"]["armed"]["payback_public"] = data.get("armed_payback_public", False)
    c["aggravated_crimes"]["fallback_to_away"] = data.get("fallback_to_away", False)

    c["action"]["enabled"] = data.get("action_enabled", False)
    c["action"]["type"] = data.get("action_type", "community_service")
    c["action"]["sub_option"] = data.get("action_sub", "")

    c.setdefault("away_action", {})
    c["away_action"]["enabled"] = data.get("away_action_enabled", False)
    c["away_action"]["type"] = data.get("away_action_type", "drug_manufacturing")

    c["payback_enabled"] = data.get("payback_enabled", False)

    c.setdefault("misc", {})
    c["misc"]["logout_on_stop"] = data.get("logout_on_stop", True)
    c["misc"]["relog_on_session_expire"] = data.get("relog_on_session_expire", True)

    cfg.save(c)
    if bot.is_running():
        bot.request_reload()
    return jsonify({"ok": True})


@app.route("/start", methods=["POST"])
def start():
    bot.start()
    return jsonify({"running": True, "paused": False})


@app.route("/stop", methods=["POST"])
def stop():
    bot.stop()
    return jsonify({"running": False, "paused": False})


@app.route("/pause", methods=["POST"])
def pause():
    bot.pause()
    return jsonify({"running": True, "paused": True})


@app.route("/resume", methods=["POST"])
def resume():
    bot.resume()
    return jsonify({"running": True, "paused": False})


@app.route("/status")
def status():
    s = bot.state
    return jsonify({
        "running": bot.is_running(),
        "paused": bot.is_paused(),
        "log": s.log[-500:],
        "energy": s.energy,
        "action_ready": s.action_available(),
        "city": s.current_city,
        "home_city": s.home_city,
        "error": s.last_error,
        "rank": s.rank,
        "occupation": s.occupation,
        "health": s.health,
        "clean_money": s.clean_money,
        "dirty_money": s.dirty_money,
        "next_rank": s.next_rank,
        "rank_progress": s.rank_progress,
        "earns_24h": s.earns_24h,
        "consumables_24h": s.consumables_24h,
        "agg_pro_active": s.agg_pro_active,
        "consumables": s.consumables,
        "own_name": s.own_name,
        "earns_enabled": cfg.load().get("earns", {}).get("enabled", True),
    })


@app.route("/clear_earn_queue", methods=["POST"])
def clear_earn_queue():
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    bot.request_clear_earn_queue()
    return jsonify({"ok": True})


@app.route("/consume", methods=["POST"])
def consume():
    consume_type = request.get_json().get("type", "")
    if consume_type:
        bot.request_consume(consume_type)
    return jsonify({"ok": True})


@app.route("/screenshot")
def screenshot():
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    try:
        png = bot.request_screenshot(timeout=10.0)
        data = base64.b64encode(png).decode()
        return jsonify({"image": f"data:image/png;base64,{data}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/logs/list")
def logs_list():
    logs_dir = os.path.join(paths.data_dir(), "logs")
    files = []
    if os.path.isdir(logs_dir):
        files = sorted(
            [f for f in os.listdir(logs_dir) if f.endswith(".log")],
            reverse=True,
        )
    return jsonify({"files": files})


def _logs_dir() -> str:
    return os.path.join(paths.data_dir(), "logs")


@app.route("/logs")
def logs_index():
    logs_dir = _logs_dir()
    files = []
    if os.path.isdir(logs_dir):
        files = sorted(
            [f for f in os.listdir(logs_dir) if f.endswith(".log")],
            reverse=True,
        )
    if not files:
        return "<html><body style='font-family:sans-serif;color:#aaa;padding:20px'>No log files found.</body></html>"
    return logs_viewer(files[0])


@app.route("/logs/<filename>")
def logs_viewer(filename):
    logs_dir = _logs_dir()
    files = []
    if os.path.isdir(logs_dir):
        files = sorted(
            [f for f in os.listdir(logs_dir) if f.endswith(".log")],
            reverse=True,
        )
    safe = os.path.basename(filename)
    if safe not in files:
        abort(404)
    path = os.path.join(logs_dir, safe)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = []
    return render_template("log.html", filename=safe, log_files=files,
                           lines=lines, line_count=len(lines))


def run():
    app.run(host="0.0.0.0", port=8080, debug=False)
