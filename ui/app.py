"""
Flask web UI for bot configuration and control.
"""

import sys
import os
import base64
import subprocess
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template, request, jsonify, abort
import config as cfg
import bot
import paths
import players as pl
import character_history as ch
import trait_requirements as tr

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
    c["aggravated_crimes"]["primary"]["energy_threshold"] = float(data.get("primary_threshold", 50))
    c["aggravated_crimes"].setdefault("away_crime", {})
    c["aggravated_crimes"]["away_crime"]["crime"] = data.get("away_crime", "pickpocket")
    c["aggravated_crimes"]["away_crime"]["energy_threshold"] = float(data.get("away_threshold", 50))
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

    c["payback_mode"] = data.get("payback_mode", "nobody")

    c.setdefault("players", {})
    c["players"]["enabled"] = data.get("player_list_enabled", True)
    c["players"]["refresh_interval_minutes"] = int(data.get("player_refresh_interval", 30))

    c.setdefault("consumables", {})
    c["consumables"]["timer_limit"] = data.get("consume_timer_limit", "00:00")
    c["consumables"]["auto_consume"] = data.get("auto_consume", False)
    c["consumables"]["auto_consumable"] = data.get("auto_consumable", "")
    c["consumables"]["consumable_limit"] = int(data.get("consumable_limit", 33))
    c["consumables"]["buffer"] = int(data.get("consumable_buffer", 0))
    c["consumables"]["smart_consumables"] = data.get("smart_consumables", False)

    c.setdefault("promo", {})
    c["promo"]["monitor_top_job"] = data.get("monitor_top_job", False)
    c["promo"]["top_job_thread_id"] = data.get("promo_thread_id", "")

    c.setdefault("jail", {})
    prev_duty = c["jail"].get("duty", "laundry")
    c["jail"]["enabled"] = data.get("jail_enabled", False)
    c["jail"]["duty"] = data.get("jail_duty", "laundry")
    c["jail"]["action"] = data.get("jail_action", "gym")
    c["jail"]["use_consumables"] = data.get("jail_use_consumables", False)
    if c["jail"]["duty"] != prev_duty and bot.is_running():
        bot.request_clear_jail_duty_queue()

    c.setdefault("misc", {})
    c["misc"]["logout_on_stop"] = data.get("logout_on_stop", True)
    c["misc"]["relog_on_session_expire"] = data.get("relog_on_session_expire", True)
    c["misc"]["min_cash_on_hand"] = int(data.get("min_cash_on_hand", 0))
    c["misc"]["headless"] = data.get("headless", False)

    c.setdefault("character_history", {})
    c["character_history"]["enabled"] = data.get("char_history_enabled", False)
    c["character_history"]["refresh_interval_minutes"] = int(data.get("char_history_interval", 30))

    c.setdefault("autobuy", {})
    c["autobuy"]["enabled"] = data.get("autobuy_enabled", False)
    c["autobuy"].setdefault("drugs", {})
    _AB_DRUGS = ["marijuana", "ecstasy", "acid", "speed", "pice", "heroin", "cocaine"]
    for key in _AB_DRUGS:
        c["autobuy"]["drugs"].setdefault(key, {})
        if f"autobuy_price_{key}" in data:
            c["autobuy"]["drugs"][key]["max_price"] = int(data[f"autobuy_price_{key}"])
        if f"autobuy_qty_{key}" in data:
            c["autobuy"]["drugs"][key]["max_qty"] = int(data[f"autobuy_qty_{key}"])

    c.setdefault("gym", {})
    c["gym"]["enabled"] = data.get("gym_enabled", False)
    c["gym"]["activity"] = data.get("gym_activity", "weights")
    c["gym"]["auto_travel"] = data.get("gym_auto_travel", False)

    c.setdefault("case_work", {})
    c["case_work"]["enabled"] = data.get("case_work_enabled", False)
    c["case_work"].setdefault("hospital", {})
    c["case_work"]["hospital"]["poll_interval"] = max(31, int(data.get("hospital_poll_interval", 31)))
    if data.get("hospital_tasks"):
        c["case_work"]["hospital"]["tasks"] = data["hospital_tasks"]
    c["case_work"].setdefault("fire", {})
    c["case_work"]["fire"]["poll_interval"] = max(31, int(data.get("fire_poll_interval", 31)))

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


def _is_git_repo() -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True, cwd=paths.resource_dir(),
        )
        return r.returncode == 0
    except FileNotFoundError:
        return False


def _git_run(*args) -> "tuple[int, str]":
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=paths.resource_dir())
    return r.returncode, (r.stdout + r.stderr).strip()


def _get_last_gym_use() -> float:
    try:
        from tasks.gym import load_last_gym_use
        return load_last_gym_use()
    except Exception:
        return 0.0


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
        "bank_balance": s.bank_balance,
        "next_rank": s.next_rank,
        "rank_progress": s.rank_progress,
        "earns_24h": s.earns_24h,
        "consumables_24h": s.consumables_24h,
        "agg_pro_active": s.agg_pro_active,
        "server_time": s.server_time.strftime("%m/%d/%Y %I:%M:%S %p") if s.server_time else None,
        "timers": {
            k: {"ready": v["ready"], "end": v["end"].strftime("%m/%d/%Y %I:%M:%S %p") if v.get("end") else None}
            for k, v in s.timers.items()
        },
        "consumables": s.consumables,
        "own_name": s.own_name,
        "earns_enabled": cfg.load().get("earns", {}).get("enabled", True),
        "current_task": s.current_task,
        "in_jail": s.in_jail,
        "jail_rank": s.jail_rank,
        "jail_consumables": s.jail_consumables,
        "jail_release_secs": s.jail_release_secs,
        "hold_action_timer": s.hold_action_timer,
        "has_new_journals": s.has_new_journals,
        "journals_updated_at": s.journals_updated_at,
        "last_gym_use": _get_last_gym_use(),
        "is_git_repo": _is_git_repo(),
        "flight_departs_at": s.flight_departs_at,
        "vehicle_health": s.vehicle_health,
    })


@app.route("/clear_earn_queue", methods=["POST"])
def clear_earn_queue():
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    bot.request_clear_earn_queue()
    return jsonify({"ok": True})


@app.route("/clear_jail_duty_queue", methods=["POST"])
def clear_jail_duty_queue():
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    bot.request_clear_jail_duty_queue()
    return jsonify({"ok": True})


@app.route("/consume", methods=["POST"])
def consume():
    consume_type = request.get_json().get("type", "")
    if consume_type:
        bot.request_consume(consume_type)
    return jsonify({"ok": True})


@app.route("/deposit", methods=["POST"])
def deposit():
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    bot.request_deposit()
    return jsonify({"ok": True})


@app.route("/withdraw", methods=["POST"])
def withdraw():
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    amount = int(request.get_json().get("amount", 0))
    if amount <= 0:
        return jsonify({"error": "Amount must be greater than zero."}), 400
    bot.request_withdraw(amount)
    return jsonify({"ok": True})


@app.route("/tasks/online_population")
def tasks_online_population():
    return jsonify(bot.online_population())


@app.route("/tasks/jail_inmates_check")
def tasks_jail_inmates_check():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running to check jail."}), 400
    try:
        result = bot.request_jail_inmates(timeout=15.0)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tasks/jailbreak_plan", methods=["POST"])
def tasks_jailbreak_plan():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    data = request.get_json()
    target = data.get("target", "").strip()
    partner = data.get("partner", "").strip()
    hold = bool(data.get("hold_action_timer", False))
    if not target:
        return jsonify({"error": "Target is required."}), 400
    if not partner:
        return jsonify({"error": "Partner is required."}), 400
    bot.request_jailbreak_plan(target, partner, hold)
    return jsonify({"ok": True})


@app.route("/tasks/jailbreak_execute", methods=["POST"])
def tasks_jailbreak_execute():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    bot.request_jailbreak_execute()
    return jsonify({"ok": True})


@app.route("/tasks/jailbreak_calloff", methods=["POST"])
def tasks_jailbreak_calloff():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    bot.request_jailbreak_calloff()
    return jsonify({"ok": True})


@app.route("/tasks/archive_journals", methods=["POST"])
def tasks_archive_journals():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    data = request.get_json(silent=True) or {}
    pages = data.get("pages")
    if pages is not None:
        try:
            pages = int(pages)
        except (ValueError, TypeError):
            return jsonify({"error": "pages must be an integer"}), 400
    bot.request_archive_journals(pages)
    return jsonify({"ok": True})


@app.route("/journals")
def journals():
    from tasks.journal import _load_journals
    char = bot.state.own_name
    if not char:
        return jsonify({})
    return jsonify(_load_journals(char))


@app.route("/character_history")
def character_history():
    return jsonify(ch.load())


@app.route("/trait_requirements")
def trait_requirements():
    data = ch.load()
    result = {}
    for name, entry in tr.REQUIREMENTS.items():
        if name in tr.HIDDEN_FROM_LOCKED:
            continue
        progress = tr.evaluate_progress(name, data)
        result[name] = {
            "ranks": entry["ranks"],
            "description": entry["description"],
            "progress": progress,
        }
    return jsonify(result)


@app.route("/character_history/refresh", methods=["POST"])
def character_history_refresh():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running to refresh character history."}), 400
    bot.request_char_history_refresh()
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


@app.route("/tasks/check_warrants", methods=["POST"])
def tasks_check_warrants():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    try:
        warrants = bot.request_warrants(timeout=30.0)
        return jsonify({"warrants": warrants})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tasks/turn_in_warrant", methods=["POST"])
def tasks_turn_in_warrant():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    data = request.get_json()
    url = data.get("url", "").strip()
    case_id = data.get("case_id", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    bot.request_turn_in_warrant(url, case_id)
    return jsonify({"ok": True})


@app.route("/page_snapshot")
def page_snapshot():
    import urls as _urls
    html = bot.state.page_html
    if not html:
        return "No page loaded yet.", 204
    base_tag = f'<base href="{_urls.BASE_URL}/">'
    if "<head>" in html:
        html = html.replace("<head>", f"<head>{base_tag}", 1)
    else:
        html = base_tag + html
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


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


@app.route("/logs/lines/<filename>")
def logs_lines(filename):
    logs_dir = _logs_dir()
    safe = os.path.basename(filename)
    path = os.path.join(logs_dir, safe)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        lines = []
    return jsonify({"lines": lines})


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


@app.route("/players")
def players_page():
    store = pl.load()
    active_count = sum(1 for p in store["players"].values() if p.get("active"))
    groups = store.get("groups", [])
    return render_template(
        "players.html",
        players=store["players"],
        lists=store["lists"],
        groups=groups,
        last_updated=store.get("last_updated"),
        active_count=active_count,
    )


@app.route("/players/refresh", methods=["POST"])
def players_refresh():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running to refresh player list."}), 400
    count = pl.refresh()
    store = pl.load()
    return jsonify({"active_count": count, "last_updated": store.get("last_updated")})


@app.route("/players/assign", methods=["POST"])
def players_assign():
    data = request.get_json()
    pl.set_assignment(data["username"], data["context"], data.get("value", ""))
    return jsonify({"ok": True})


@app.route("/promo/bar_threads")
def promo_bar_threads():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running to fetch bar threads."}), 400
    try:
        result = bot.request_bar_threads(timeout=15.0)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/players/groups/create", methods=["POST"])
def players_groups_create():
    data = request.get_json()
    ok = pl.create_group(data.get("name", "").strip(), data.get("color", "#888888"))
    return jsonify({"ok": ok, "error": "Name already exists." if not ok else None})


@app.route("/players/groups/delete", methods=["POST"])
def players_groups_delete():
    data = request.get_json()
    pl.delete_group(data.get("name", ""))
    return jsonify({"ok": True})


@app.route("/players/groups/update_color", methods=["POST"])
def players_groups_update_color():
    data = request.get_json()
    pl.update_group_color(data.get("name", ""), data.get("color", "#888888"))
    return jsonify({"ok": True})


@app.route("/players/set_group", methods=["POST"])
def players_set_group():
    data = request.get_json()
    pl.set_player_group(data["username"], data.get("group", ""))
    return jsonify({"ok": True})


@app.route("/players/group_mass_assign", methods=["POST"])
def players_group_mass_assign():
    data = request.get_json()
    count = pl.group_mass_assign(data["group"], data["context"], data.get("assignment", ""))
    return jsonify({"ok": True, "count": count})


@app.route("/players/import", methods=["POST"])
def players_import():
    data = request.get_json()
    names = [n.strip() for n in data.get("names", []) if n.strip()]
    context = data.get("context", "agg_crimes")
    assignment = data.get("assignment", "blacklist")

    store = pl.load()
    known = {k.lower(): k for k in store["players"]}

    matched = []
    unmatched = []
    for name in names:
        canonical = known.get(name.lower())
        if canonical:
            pl.set_assignment(canonical, context, assignment)
            matched.append(canonical)
        else:
            unmatched.append(name)

    return jsonify({"assigned": len(matched), "matched": matched, "unmatched": unmatched})


@app.route("/tasks/travel_destinations")
def tasks_travel_destinations():
    method = request.args.get("method", "airport")
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    import browser as _browser
    from bs4 import BeautifulSoup as _BS
    import urls as _urls
    try:
        if method == "own_vehicle":
            html = _browser.navigate(_urls.BASE_URL + "/travel/travel.asp")
            soup = _BS(html, "html.parser")
            sel = soup.find("select", attrs={"name": "vehicletravel"})
            if not sel:
                return jsonify({"destinations": []})
            opts = [
                {"value": o["value"], "label": o.get_text(strip=True)}
                for o in sel.find_all("option") if o.get("value")
            ]
        else:
            html = _browser.navigate(_urls.BASE_URL + "/travel/airport.asp")
            soup = _BS(html, "html.parser")
            sel = soup.find("select", attrs={"name": "destination"})
            if not sel:
                return jsonify({"destinations": []})
            opts = [
                {
                    "value": o["value"],
                    "label": o.get_text(strip=True),
                    "costs": o.get("data-costs", ""),
                    "minutes": o.get("data-minutes", ""),
                }
                for o in sel.find_all("option")
                if o.get("value") and o.get("value") != "0"
            ]
        return jsonify({"destinations": opts})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/tasks/travel", methods=["POST"])
def tasks_travel():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    data = request.get_json()
    target = data.get("target_city", "").strip()
    method = data.get("method", "airport")
    if not target:
        return jsonify({"error": "target_city is required."}), 400
    bot.request_travel(target, method)
    return jsonify({"ok": True})


@app.route("/check_update")
def check_update():
    if not _is_git_repo():
        return jsonify({"error": "Not a git repository."}), 400
    rc, out = _git_run("fetch", "origin")
    if rc != 0:
        return jsonify({"error": f"git fetch failed: {out}"}), 500
    rc, behind = _git_run("rev-list", "--count", "HEAD..origin/main")
    if rc != 0:
        return jsonify({"error": "Could not compare versions."}), 500
    count = int(behind.strip() or "0")
    if count == 0:
        return jsonify({"up_to_date": True, "commits_behind": 0})
    rc, log = _git_run("log", "--oneline", f"HEAD..origin/main")
    return jsonify({"up_to_date": False, "commits_behind": count, "log": log})


@app.route("/apply_update", methods=["POST"])
def apply_update():
    if not _is_git_repo():
        return jsonify({"error": "Not a git repository."}), 400
    if bot.is_running():
        return jsonify({"error": "Stop the bot before applying an update."}), 400
    rc, out = _git_run("pull", "--ff-only", "origin", "main")
    if rc != 0:
        return jsonify({"error": f"git pull failed: {out}"}), 500
    return jsonify({"ok": True, "output": out})


def run():
    import config as _cfg
    port = int(_cfg.get_env_var("UI_PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
