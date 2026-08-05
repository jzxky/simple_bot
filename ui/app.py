"""
Flask web UI for bot configuration and control.
"""

import sys
import os
import subprocess
if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, render_template, request, jsonify, abort, send_file, session, redirect, url_for
import config as cfg
import bot
import paths
import players as pl
import character_history as ch
import trait_requirements as tr

NOTIFICATION_EVENTS = [
    ("bionics_in_stock",       "Bionics in stock"),
    ("bionics_purchased",      "Bionic purchased"),
    ("bionics_restock",        "Bionics restock detected"),
    ("weapon_store_in_stock",  "Weapon store in stock"),
    ("weapon_store_purchased", "Weapon store purchased"),
    ("weapon_store_restock",   "Weapon store restock detected"),
    ("promotion_success",   "Rank promotion"),
    ("auto_promo",          "Auto-promotion triggered"),
    ("session_expired",     "Session expired"),
    ("jailed",              "Went to jail"),
    ("targets_exhausted",   "Crime targets exhausted"),
    ("mhs_protected",       "MHS Protection Attempt"),
    ("warrants_outstanding", "Outstanding warrants (travel blocked)"),
    ("agg_not_available",   "Agg crime not available"),
    ("dog_trains_unavailable", "Dog trains unavailable"),
]

_ui_root = os.path.join(paths.resource_dir(), "ui")
app = Flask(__name__,
            template_folder=os.path.join(_ui_root, "templates"),
            static_folder=os.path.join(_ui_root, "static"))
app.secret_key = cfg.get_or_create_secret_key()


@app.before_request
def require_pin():
    if not cfg.get_pin_required():
        return
    if request.endpoint in ("login", "static"):
        return
    if request.path == "/war" or request.path.startswith("/api/war/"):
        if cfg.load().get("war_mode", {}).get("skip_pin", False):
            return
    if not session.get("authenticated"):
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if not cfg.get_pin_required():
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        if request.form.get("pin") == cfg.get_pin():
            session["authenticated"] = True
            return redirect(url_for("index"))
        error = "Incorrect PIN"
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def index():
    c = cfg.load()
    return render_template("index.html", config=c, notification_events=NOTIFICATION_EVENTS,
                           pin_required=cfg.get_pin_required(), ui_pin=cfg.get_pin())


def _merge_changed(target: dict, before: dict, after: dict):
    """Copy into `target` only the leaves that differ between `before` and
    `after` (i.e. the ones this client actually changed). Recurses into nested
    dicts so untouched sibling keys — and any values written by the bot in the
    background — are preserved."""
    for k, av in after.items():
        bv = before.get(k) if isinstance(before, dict) else None
        if isinstance(av, dict) and isinstance(bv, dict):
            tv = target.get(k)
            if not isinstance(tv, dict):
                tv = {}
                target[k] = tv
            _merge_changed(tv, bv, av)
        elif av != bv:
            target[k] = av
    if isinstance(before, dict):
        for k in before:
            if k not in after:
                target.pop(k, None)


def _apply_payload(c: dict, data: dict) -> dict:
    """Populate config dict `c` from a settings payload `data`. Pure — no env
    writes, no bot signals, no persistence (those are handled by save())."""
    c["earns"]["enabled"] = data.get("earns_enabled", False)
    c["earns"]["earn_type"] = data.get("earn_type", "surgeon")
    c["earns"]["earn_mode"] = data.get("earn_mode", "auto")

    if "earn_planner_limits" in data and isinstance(data["earn_planner_limits"], dict):
        import earn_planner as _ep
        clean = {}
        for k, v in data["earn_planner_limits"].items():
            if k not in _ep.HISTORY_NAME:
                continue
            try:
                n = int(v)
            except (TypeError, ValueError):
                continue
            if n > 0:
                clean[k] = n
        c.setdefault("earn_planner", {})["limits"] = clean

    c["aggravated_crimes"]["enabled"] = data.get("crimes_enabled", False)
    c["aggravated_crimes"]["primary"]["crime"] = data.get("primary_crime", "pickpocket")
    c["aggravated_crimes"]["primary"]["energy_threshold"] = float(data.get("primary_threshold", 50))
    c["aggravated_crimes"].setdefault("away_crime", {})
    c["aggravated_crimes"]["away_crime"]["crime"] = data.get("away_crime", "pickpocket")
    c["aggravated_crimes"]["away_crime"]["energy_threshold"] = float(data.get("away_threshold", 50))
    c["aggravated_crimes"].setdefault("armed", {})
    c["aggravated_crimes"]["armed"]["agg_private"] = data.get("armed_agg_private", False)
    c["aggravated_crimes"]["armed"]["agg_drug_house"] = data.get("armed_agg_drug_house", False)
    c["aggravated_crimes"].setdefault("torch", {})
    c["aggravated_crimes"]["torch"]["torch_private"] = data.get("torch_private", False)
    c["aggravated_crimes"]["torch"]["torch_payback_public"] = data.get("torch_payback_public", "everyone")
    c["aggravated_crimes"]["torch"]["torch_payback_private"] = data.get("torch_payback_private", "everyone")
    c["aggravated_crimes"]["fallback_to_away"] = data.get("fallback_to_away", False)

    c["action"]["enabled"] = data.get("action_enabled", False)
    c["action"]["type"] = data.get("action_type", "community_service")
    c["action"]["sub_option"] = data.get("action_sub", "")
    c["action"]["fallback_action"] = data.get("action_fallback", "")
    c["action"]["career_training_stop_at_14"] = data.get("career_training_stop_at_14", False)

    c.setdefault("away_action", {})
    c["away_action"]["enabled"] = data.get("away_action_enabled", False)
    c["away_action"]["type"] = data.get("away_action_type", "drug_manufacturing")

    c.setdefault("laundering", {})
    c["laundering"]["enabled"] = data.get("laundering_enabled", False)
    c["laundering"]["launder_amount"] = int(data.get("launder_amount", 0) or 0)
    c["laundering"]["preferred_contacts"] = data.get("laundering_preferred_contacts", [])

    c["payback_mode"] = data.get("payback_mode", "nobody")

    c.setdefault("players", {})
    c["players"]["enabled"] = data.get("player_list_enabled", True)
    c["players"]["refresh_interval_minutes"] = int(data.get("player_refresh_interval", 30))
    c["players"]["whitelist_bolds"] = data.get("player_whitelist_bolds", True)

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
    c["promo"].setdefault("auto_promo", {})
    c["promo"]["auto_promo"]["enabled"] = data.get("auto_promo_enabled", False)
    if "promo_choices" in data and isinstance(data.get("promo_choices"), dict):
        c["promo"]["choices"] = data["promo_choices"]

    c.setdefault("crossroads", {})
    c["crossroads"]["enabled"] = data.get("crossroads_enabled", False)
    c["crossroads"]["selection"] = data.get("crossroads_selection", "current")

    c.setdefault("war_mode", {})
    c["war_mode"]["enabled"] = data.get("war_mode_enabled", False)
    c["war_mode"]["skip_pin"] = data.get("war_mode_skip_pin", False)

    c.setdefault("jail", {})
    c["jail"]["enabled"] = data.get("jail_enabled", False)
    c["jail"]["duty"] = data.get("jail_duty", "laundry")
    c["jail"]["action"] = data.get("jail_action", "gym")
    c["jail"]["use_consumables"] = data.get("jail_use_consumables", False)
    c["jail"]["auto_jail_time"] = data.get("auto_jail_time", "off")
    c["jail"]["use_warrants"] = data.get("use_warrants", False)
    c["jail"]["auto_warrant_handling"] = data.get("auto_warrant_handling", "none")
    c["jail"]["auto_jail_partner"] = data.get("auto_jail_partner", "")

    c.setdefault("misc", {})
    c["misc"]["logout_on_stop"] = data.get("logout_on_stop", True)
    c["misc"]["relog_on_session_expire"] = data.get("relog_on_session_expire", True)
    c["misc"]["min_cash_on_hand"] = int(data.get("min_cash_on_hand", 0))
    c["misc"]["headless"] = data.get("headless", False)
    c["misc"]["show_scheduler"] = data.get("show_scheduler", False)
    c["misc"]["debug_logging"] = data.get("debug_logging", False)
    c.setdefault("event_boss", {})
    c["event_boss"]["enabled"] = data.get("event_boss_enabled", False)
    import event_consumables as _ec
    c["event_boss"].setdefault("consume", {})
    for _name in _ec.EVENT_ORDER:
        c["event_boss"]["consume"][_name] = data.get(f"event_consume_{_name}", False)

    c.setdefault("sync", {})
    c["sync"]["enabled"]          = data.get("sync_enabled", False)
    c["sync"]["server_url"]       = data.get("sync_server_url", "").strip()
    c["sync"]["interval_minutes"] = int(data.get("sync_interval", 2))
    c["sync"]["sync_online_time"] = data.get("sync_online_time", True)
    c["sync"]["sync_lists"]       = data.get("sync_lists", True)
    c["sync"]["sync_groups"]      = data.get("sync_groups", True)

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

    c.setdefault("casino", {})
    c["casino"]["enabled"] = data.get("casino_enabled", False)
    c["casino"]["activity"] = data.get("casino_activity", "slots")
    c["casino"]["bet_amount"] = max(100, min(99999, int(data.get("casino_bet_amount", 100) or 100)))
    c["casino"]["auto_travel"] = data.get("casino_auto_travel", False)

    c.setdefault("smart_travel", {})
    c["smart_travel"]["enabled"] = data.get("smart_travel_enabled", False)
    c["smart_travel"]["store_priority"] = data.get("smart_travel_store_priority", "bionics")
    c["smart_travel"]["window_vs_activity"] = data.get("smart_travel_window_vs_activity", "windows")
    c["smart_travel"]["home"] = data.get("smart_travel_home", "home_city")

    c.setdefault("bionics", {})
    c["bionics"]["enabled"] = data.get("bionics_enabled", False)
    c["bionics"]["wanted_items"] = data.get("bionics_wanted_items", [])
    c["bionics"]["check_interval_window_minutes"] = max(1, min(30, int(data.get("bionics_interval_window", 5) or 5)))
    c["bionics"]["check_interval_no_window_minutes"] = max(1, min(30, int(data.get("bionics_interval_no_window", 16) or 16)))
    c["bionics"]["use_time_window"] = data.get("bionics_use_time_window", False)
    c["bionics"]["window_start"] = data.get("bionics_window_start", "00:00")
    c["bionics"]["window_end"] = data.get("bionics_window_end", "23:59")
    c["bionics"]["priority_order"] = data.get("bionics_priority_order", [])
    c["bionics"]["auto_restock"] = data.get("bionics_auto_restock", False)

    c.setdefault("weapon_store", {})
    c["weapon_store"]["enabled"] = data.get("weapon_store_enabled", False)
    c["weapon_store"]["wanted_items"] = data.get("weapon_store_wanted_items", [])
    c["weapon_store"]["priority_order"] = data.get("weapon_store_priority_order", [])
    c["weapon_store"]["check_interval_window_minutes"] = max(1, min(30, int(data.get("weapon_store_interval_window", 5) or 5)))
    c["weapon_store"]["check_interval_no_window_minutes"] = max(1, min(30, int(data.get("weapon_store_interval_no_window", 16) or 16)))
    c["weapon_store"]["use_time_window"] = data.get("weapon_store_use_time_window", False)
    c["weapon_store"]["window_start"] = data.get("weapon_store_window_start", "00:00")
    c["weapon_store"]["window_end"] = data.get("weapon_store_window_end", "23:59")
    c["weapon_store"]["auto_restock"] = data.get("weapon_store_auto_restock", False)

    c.setdefault("case_work", {})
    c["case_work"]["enabled"] = data.get("case_work_enabled", False)
    c["case_work"].setdefault("hospital", {})
    c["case_work"]["hospital"]["poll_interval"] = max(31, int(data.get("hospital_poll_interval", 31)))
    if data.get("hospital_tasks"):
        c["case_work"]["hospital"]["tasks"] = data["hospital_tasks"]
    c["case_work"].setdefault("fire", {})
    c["case_work"]["fire"]["poll_interval"] = max(31, int(data.get("fire_poll_interval", 31)))
    c["case_work"].setdefault("engineering", {})
    c["case_work"]["engineering"]["poll_interval"] = max(31, int(data.get("engineering_poll_interval", 31)))
    c["case_work"].setdefault("banking", {})
    c["case_work"]["banking"]["poll_interval"] = max(31, int(data.get("banking_poll_interval", 60)))
    if data.get("engineering_tasks"):
        c["case_work"]["engineering"]["tasks"] = data["engineering_tasks"]

    import re as _re
    c.setdefault("banking", {})
    c["banking"]["auto_invest_enabled"] = data.get("banking_auto_invest_enabled", False)
    c["banking"]["investment_term"] = data.get("banking_investment_term", "3,2.25")
    raw_amt = _re.sub(r"[^0-9]", "", str(data.get("banking_invest_amount", 0) or "0"))
    c["banking"]["invest_amount"] = min(int(raw_amt or 0), 1500000)

    c.setdefault("notifications", {})
    for slug, _ in NOTIFICATION_EVENTS:
        c["notifications"][slug] = data.get(f"notif_{slug}", False)

    return c


@app.route("/save", methods=["POST"])
def save():
    import copy
    import settings_rev
    data = request.get_json() or {}
    base = data.pop("_base", None)

    c_live = cfg.load()
    prev_duty = c_live.get("jail", {}).get("duty", "laundry")

    if isinstance(base, dict) and base:
        # Partial/diff apply: only overwrite the leaves this client changed vs
        # the snapshot it rendered from — never touching other tabs' fields or
        # values the bot wrote in the background.
        before = _apply_payload(copy.deepcopy(c_live), base)
        after  = _apply_payload(copy.deepcopy(c_live), data)
        _merge_changed(c_live, before, after)
        c = c_live
        # Earn planner limits are a self-contained dict — always write directly
        # to avoid diff-merge issues with mutable object references.
        if "earn_planner_limits" in data and isinstance(data["earn_planner_limits"], dict):
            import earn_planner as _ep
            clean = {}
            for k, v in data["earn_planner_limits"].items():
                if k not in _ep.HISTORY_NAME:
                    continue
                try:
                    n = int(v)
                except (TypeError, ValueError):
                    continue
                if n > 0:
                    clean[k] = n
            c.setdefault("earn_planner", {})["limits"] = clean
        creds_changed = (data.get("email") != base.get("email")
                         or data.get("password") != base.get("password"))
        pin_changed = (data.get("pin_required") != base.get("pin_required")
                       or data.get("ui_pin") != base.get("ui_pin"))
    else:
        # Legacy full apply (no base sent — e.g. very first save).
        c = _apply_payload(c_live, data)
        creds_changed = True
        pin_changed = True

    if creds_changed or pin_changed:
        cfg.save_env(data.get("email", ""), data.get("password", ""),
                     pin_required=data.get("pin_required"),
                     pin=data.get("ui_pin"))

    new_duty = c.get("jail", {}).get("duty", "laundry")
    _MANUAL_DUTIES = {"makeshank", "digtunnel"}
    if new_duty != prev_duty and bot.is_running():
        bot.request_clear_jail_duty_queue()
        if prev_duty in _MANUAL_DUTIES and new_duty not in _MANUAL_DUTIES:
            bot.request_run_jail_duties()

    cfg.save(c)
    settings_rev.bump()
    if bot.is_running():
        bot.request_reload()
    return jsonify({"ok": True, "settings_rev": settings_rev.get()})


@app.route("/notifications/dismiss", methods=["POST"])
def notif_dismiss():
    nid = (request.get_json() or {}).get("id")
    if nid:
        bot.state.notifications = [n for n in bot.state.notifications if n["id"] != nid]
    return jsonify({"ok": True})


@app.route("/notifications/clear", methods=["POST"])
def notif_clear():
    bot.state.notifications = []
    return jsonify({"ok": True})


@app.route("/travel/clear-warrant-cooldown", methods=["POST"])
def clear_warrant_cooldown():
    import executor
    executor._travel_warrant_cooldown_until = 0.0
    return jsonify({"ok": True})


@app.route("/earn_catalog", methods=["GET"])
def earn_catalog_get():
    import json, os
    path = os.path.join(paths.data_dir(), "available_earns.json")
    if not os.path.exists(path):
        return jsonify([])
    try:
        with open(path, encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify([])


@app.route("/earn_catalog", methods=["POST"])
def earn_catalog_post():
    import json, os
    data = request.get_json() or []
    path = os.path.join(paths.data_dir(), "available_earns.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/start", methods=["POST"])
def start():
    bot.start()
    return jsonify({"running": True, "paused": False})


@app.route("/stop", methods=["POST"])
def stop():
    bot.stop()
    return jsonify({"running": False, "paused": False})


@app.route("/cancel-snipe", methods=["POST"])
def cancel_snipe():
    bot.cancel_snipe()
    return jsonify({"ok": True})


@app.route("/banklaunder/bulk_add", methods=["POST"])
def banklaunder_bulk_add():
    if not bot.is_running():
        return jsonify({"ok": False, "error": "Bot is not running."})
    bot.request_bulk_launder()
    return jsonify({"ok": True})


_GANGSTER_RANKS = {
    "dealer", "giovane d'honore", "giovane d`honore", "enforcer", "piciotto",
    "sgarrista", "capodecima", "caporegime", "boss", "don", "godfather",
    "capo di tutti capi",
}


def _is_gangster(occupation: str, rank: str = "") -> bool:
    """Robust gangster check: occupation contains 'gangster' (handles whitespace/
    casing) or the rank is a known gangster rank (in case occupation shows a rank)."""
    occ = (occupation or "").lower()
    if "gangster" in occ:
        return True
    return (rank or "").strip().lower() in _GANGSTER_RANKS


@app.route("/jail/partner_candidates")
def jail_partner_candidates():
    """Valid jail-break partners from the player-list DB (including offline players,
    sorted by character age ascending)."""
    import player_db as _db
    s = bot.state
    own = (s.own_name if s else "") or ""
    self_gangster = _is_gangster(s.occupation if s else "", s.rank if s else "")
    home = ((s.home_city if s else "") or "").lower()
    rows = []
    for p in _db.get_all_players():
        if not p.get("active"):
            continue
        name = p.get("username")
        if not name or name == own:
            continue
        p_gangster = _is_gangster(p.get("occupation", ""), p.get("rank", ""))
        if self_gangster:
            # Gangster: any gangster character.
            if not p_gangster:
                continue
        else:
            # Non-gangster: only other non-gangster characters in the same home city.
            if p_gangster:
                continue
            if (p.get("homecity") or "").lower() != home:
                continue
        rows.append((p.get("character_age") or 0, name))
    rows.sort(key=lambda r: r[0])  # character age ascending
    return jsonify({
        "partners": [n for _, n in rows],
        # Diagnostics for troubleshooting the filter:
        "self": {"name": own, "occupation": (s.occupation if s else ""),
                 "rank": (s.rank if s else ""), "home_city": (s.home_city if s else ""),
                 "is_gangster": self_gangster},
    })


@app.route("/jail/auto_jail_check", methods=["POST"])
def jail_auto_check():
    if not bot.is_running():
        return jsonify({"ok": False, "error": "Bot is not running."})
    bot.request_auto_jail_check()
    return jsonify({"ok": True})


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


def _get_respect_data() -> dict:
    try:
        from tasks.respect import load_respect_data
        return load_respect_data()
    except Exception:
        return {"respect_pct": None, "last_check": 0.0}


def _get_casino_release_at() -> float:
    try:
        from tasks.casino import load_casino_release_at
        return load_casino_release_at()
    except Exception:
        return 0.0


def _get_banking_mature_at() -> float:
    try:
        from tasks.banking import load_mature_date
        return load_mature_date()
    except Exception:
        return 0.0


def _get_bionics_next_check_at(state) -> "float | None":
    import time as _time
    task = bot.get_bionics_task()
    if not task or task.last_checked_at <= 0:
        return None
    import store_windows
    b = cfg.load().get("bionics", {})
    interval_secs = store_windows.interval_secs(b, state.ingame_mins)
    next_at = task.last_checked_at + interval_secs

    if b.get("use_time_window", False) and state.server_time is not None:
        start = b.get("window_start", "00:00")
        end   = b.get("window_end",   "23:59")
        start_mins = int(start[:2]) * 60 + int(start[3:])
        end_mins   = int(end[:2])   * 60 + int(end[3:])
        ingame = state.ingame_mins
        if start_mins < end_mins:
            _outside = ingame is not None and not (start_mins < ingame < end_mins)
        else:
            _outside = ingame is not None and not (ingame > start_mins or ingame < end_mins)
        if _outside:
            # Outside window — next check is at window start
            ingame_secs_now = (state.server_time.hour * 3600
                               + state.server_time.minute * 60
                               + state.server_time.second)
            secs_until_start = start_mins * 60 - ingame_secs_now
            if secs_until_start <= 0:
                secs_until_start += 86400  # rolls over to tomorrow
            next_at = _time.time() + secs_until_start

    return next_at


def _get_weapon_store_next_check_at(state) -> "float | None":
    import time as _time
    task = bot.get_weapon_store_task()
    if not task or task.last_checked_at <= 0:
        return None
    import store_windows
    w = cfg.load().get("weapon_store", {})
    interval_secs = store_windows.interval_secs(w, state.ingame_mins)
    next_at = task.last_checked_at + interval_secs

    if w.get("use_time_window", False) and state.server_time is not None:
        start = w.get("window_start", "00:00")
        end   = w.get("window_end",   "23:59")
        start_mins = int(start[:2]) * 60 + int(start[3:])
        end_mins   = int(end[:2])   * 60 + int(end[3:])
        ingame = state.ingame_mins
        if start_mins < end_mins:
            _outside = ingame is not None and not (start_mins < ingame < end_mins)
        else:
            _outside = ingame is not None and not (ingame > start_mins or ingame < end_mins)
        if _outside:
            ingame_secs_now = (state.server_time.hour * 3600
                               + state.server_time.minute * 60
                               + state.server_time.second)
            secs_until_start = start_mins * 60 - ingame_secs_now
            if secs_until_start <= 0:
                secs_until_start += 86400
            next_at = _time.time() + secs_until_start

    return next_at


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
        "action_enabled": cfg.load().get("action", {}).get("enabled", False),
        "action_type": cfg.load().get("action", {}).get("type", ""),
        "action_sub": cfg.load().get("action", {}).get("sub_option", ""),
        "action_fallback": cfg.load().get("action", {}).get("fallback_action", ""),
        "earns_enabled": cfg.load().get("earns", {}).get("enabled", True),
        "earn_type": cfg.load().get("earns", {}).get("earn_type", ""),
        "earn_mode": cfg.load().get("earns", {}).get("earn_mode", "auto"),
        "current_task": s.current_task,
        "in_jail": s.in_jail,
        "jail_rank": s.jail_rank,
        "jail_consumables": s.jail_consumables,
        "jail_release_secs": s.jail_release_secs,
        "hold_action_timer": s.hold_action_timer,
        "in_hospital": s.in_hospital,
        "cs_sentence": s.cs_sentence,
        "agg_fail_count": s.agg_fail_count(),
        "online_players": list(s.online_players),
        "local_players": list(s.local_players),
        "jail_players": list(s.jail_players),
        "has_new_journals": s.has_new_journals,
        "journals_updated_at": s.journals_updated_at,
        "event_boss_enabled": cfg.load().get("event_boss", {}).get("enabled", False),
        "event_consumables": s.event_consumables,
        "settings_rev": __import__("settings_rev").get(),
        "last_gym_use": _get_last_gym_use(),
        "casino_release_at": _get_casino_release_at(),
        "bionics_next_check_at": _get_bionics_next_check_at(s),
        "bionics_window_start": cfg.load().get("bionics", {}).get("window_start", "00:00"),
        "bionics_window_end":   cfg.load().get("bionics", {}).get("window_end",   "23:59"),
        "bionics_views": ({"current": bot.get_bionics_task().last_views[0], "max": bot.get_bionics_task().last_views[1]} if bot.get_bionics_task() and bot.get_bionics_task().last_views else None),
        "weapon_store_next_check_at": _get_weapon_store_next_check_at(s),
        "weapon_store_window_start": cfg.load().get("weapon_store", {}).get("window_start", "00:00"),
        "weapon_store_window_end":   cfg.load().get("weapon_store", {}).get("window_end",   "23:59"),
        "is_git_repo": _is_git_repo(),
        "flight_departs_at": s.flight_departs_at,
        "vehicle_health": s.vehicle_health,
        "char_history_updated_at": s.char_history_updated_at,
        "hospital_release_at": s.hospital_release_at,
        "respect_pct": _get_respect_data().get("respect_pct"),
        "respect_last_check": _get_respect_data().get("last_check", 0.0),
        "notifications": bot.state.notifications,
        "launder_cooldown": __import__("executor").launder_cooldown_remaining(),
        "banking_mature_at": _get_banking_mature_at(),
    })


@app.route("/api/shutdown", methods=["POST"])
def shutdown():
    import signal, threading
    threading.Timer(0.3, lambda: os.kill(os.getpid(), signal.SIGTERM)).start()
    return jsonify({"ok": True})


@app.route("/respect/refresh", methods=["POST"])
def respect_refresh():
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    bot.request_respect_refresh()
    return jsonify({"ok": True})


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


@app.route("/consume-event", methods=["POST"])
def consume_event():
    name = request.get_json().get("name", "")
    if name:
        bot.request_event_consume(name)
    return jsonify({"ok": True})


@app.route("/journal-action", methods=["POST"])
def journal_action():
    data = request.get_json()
    entry_id = data.get("entry_id", "")
    action_url = data.get("action_url", "")
    action_type = data.get("action_type", "")
    if action_url:
        bot.request_journal_action(entry_id, action_url, action_type)
    return jsonify({"ok": True})


@app.route("/clear-launder-cooldown", methods=["POST"])
def clear_launder_cooldown():
    import executor
    executor.clear_launder_cooldown()
    return jsonify({"ok": True})


@app.route("/toggle-monitoring", methods=["POST"])
def toggle_monitoring():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "")
    on = data.get("on", False)
    if not username:
        return jsonify({"error": "missing username"}), 400
    import player_db
    player_db.toggle_monitoring(username, on)
    return jsonify({"ok": True})


@app.route("/scrape-players", methods=["POST"])
def scrape_players():
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    bot.request_scrape_players()
    return jsonify({"ok": True})


@app.route("/players/<username>/scrape", methods=["POST"])
def scrape_player(username):
    if not bot.is_running():
        return jsonify({"error": "Bot is not running."}), 400
    bot.request_scrape_player(username)
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
    return jsonify(ch.load(request.args.get("char", "")))


@app.route("/character_history/list")
def character_history_list():
    current = bot.state.own_name if bot.state else ""
    return jsonify({"characters": ch.list_saved(), "current": current})


@app.route("/trait_requirements")
def trait_requirements():
    data = ch.load(request.args.get("char", ""))
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


@app.route("/api/interact", methods=["POST"])
def api_interact():
    if not bot.is_running():
        return jsonify({"ok": False, "message": "Bot must be running."}), 400
    data = request.get_json(force=True) or {}
    crime  = (data.get("crime") or "").strip()
    target = (data.get("target") or "").strip()
    amount = int(data.get("amount") or 0)
    if not crime or not target:
        return jsonify({"ok": False, "message": "Missing crime or target."}), 400
    try:
        result = bot.request_interact(crime, target, amount)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/profile")
def profile():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    try:
        result = bot.request_profile(timeout=30)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/navigate", methods=["POST"])
def navigate():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    bot.request_navigate(url)
    return jsonify({"ok": True})


@app.route("/repair_vehicle", methods=["POST"])
def repair_vehicle_route():
    if not bot.is_running():
        return jsonify({"error": "Bot must be running."}), 400
    bot.request_repair_vehicle()
    return jsonify({"ok": True})


@app.route("/screenshot")
def screenshot():
    import paths as _paths
    import browser as _browser
    path = _browser.SCREENSHOT_PATH
    if not os.path.exists(path):
        return "No screenshot yet.", 204
    return send_file(path, mimetype="image/png")


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


@app.route("/api/scheduler")
def api_scheduler():
    return jsonify({"tasks": bot.get_scheduler_snapshot()})



@app.route("/api/available_earns")
def api_available_earns():
    import json as _json
    path = os.path.join(paths.data_dir(), "available_earns.json")
    try:
        with open(path, encoding="utf-8") as f:
            return jsonify(_json.load(f))
    except Exception:
        return jsonify([])


@app.route("/api/earn_planner")
def api_earn_planner():
    import earn_planner as _ep
    c = cfg.load()
    limits = c.get("earn_planner", {}).get("limits", {})
    active = c.get("earns", {}).get("earn_type", "")
    return jsonify(_ep.planner_view(limits, active))


@app.route("/players")
def players_page():
    return render_template("players.html")


@app.route("/war")
def war_page():
    return render_template("war.html")


@app.route("/api/war/lists")
def api_war_lists():
    import war_mode
    st = war_mode.get_state()
    st["enabled"] = cfg.load().get("war_mode", {}).get("enabled", False)
    st["interval"] = cfg.load().get("war_mode", {}).get("monitor_interval_minutes", 5)
    st["running"] = bot.is_running()
    return jsonify(st)


@app.route("/api/war/add", methods=["POST"])
def api_war_add():
    import war_mode
    d = request.get_json(force=True) or {}
    name = d.get("name", "")
    ok, msg = war_mode.add_name(name, d.get("side", ""))
    if ok and bot.is_running():
        bot.request_ws_monitor(name.strip())  # immediate WS check for the new name
    return jsonify({"ok": ok, "message": msg}), (200 if ok else 400)


@app.route("/api/war/remove", methods=["POST"])
def api_war_remove():
    import war_mode
    d = request.get_json(force=True) or {}
    war_mode.remove_name(d.get("name", ""), d.get("side", ""))
    return jsonify({"ok": True})


@app.route("/api/war/set_whack_type", methods=["POST"])
def api_war_set_whack_type():
    import war_mode
    d = request.get_json(force=True) or {}
    war_mode.set_whack_type(d.get("name", ""), d.get("side", ""), d.get("whack_type", "Normal"))
    return jsonify({"ok": True})


@app.route("/api/war/set_whack_time", methods=["POST"])
def api_war_set_whack_time():
    import war_mode
    d = request.get_json(force=True) or {}
    war_mode.set_whack_time(d.get("name", ""), d.get("side", ""), d.get("time", ""))
    return jsonify({"ok": True})


@app.route("/api/war/set_interval", methods=["POST"])
def api_war_set_interval():
    d = request.get_json(force=True) or {}
    minutes = max(2, min(10, int(d.get("minutes", 5) or 5)))
    c = cfg.load()
    c.setdefault("war_mode", {})["monitor_interval_minutes"] = minutes
    cfg.save(c)
    return jsonify({"ok": True, "minutes": minutes})


@app.route("/api/war/check", methods=["POST"])
def api_war_check():
    if not bot.is_running():
        return jsonify({"ok": False, "message": "Bot must be running to check."}), 400
    d = request.get_json(silent=True) or {}
    bot.request_ws_monitor((d.get("name") or "").strip() or None)
    return jsonify({"ok": True})


@app.route("/api/war/clear_events", methods=["POST"])
def api_war_clear_events():
    import war_mode
    war_mode.clear_events()
    return jsonify({"ok": True})


@app.route("/api/players")
def api_players():
    import player_db as _db
    return jsonify({
        "players": _db.get_all_players(),
        "groups": _db.get_groups(),
        "last_updated": _db.get_last_updated(),
        "active_count": _db.get_active_count(),
    })


@app.route("/api/player_image/<username>")
def api_player_image(username):
    import player_images as _pi
    path = _pi.path_for_username(username)
    if not path:
        abort(404)
    return send_file(path)


@app.route("/api/players/top_jobs")
def api_top_jobs():
    import player_db as _db
    from datetime import datetime, timezone
    TOP_JOBS = [
        "Hospital Director", "Fire Chief", "Bank Manager",
        "Funeral Director", "Chief Engineer", "Commissioner-General",
    ]
    now_utc = datetime.now(timezone.utc)
    all_p = _db.get_all_players()
    _RANK_JOBS = {"Commissioner-General"}
    holders = [p for p in all_p
               if (p.get("occupation") in TOP_JOBS or p.get("rank") in _RANK_JOBS)
               and p.get("active", 1)]
    result = []
    for p in holders:
        matched_job = p.get("rank") if p.get("rank") in _RANK_JOBS else p.get("occupation")
        history = _db.get_career_history(p["username"])
        duration_secs = None
        for entry in history:
            if entry.get("occupation") == p["occupation"] and entry.get("homecity") == p.get("homecity"):
                ts = entry.get("ts", "")
                if ts:
                    try:
                        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        duration_secs = max(0, int((now_utc - dt).total_seconds()))
                    except Exception:
                        pass
                break
        result.append({
            "username": p["username"],
            "occupation": matched_job,
            "homecity": p.get("homecity", ""),
            "rank": p.get("rank", ""),
            "duration_secs": duration_secs,
        })
    return jsonify({"holders": result, "jobs": TOP_JOBS})


@app.route("/api/players/<username>/history")
def api_player_history(username):
    import player_db as _db
    return jsonify({"history": _db.get_career_history(username)})


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


@app.route("/players/set_field", methods=["POST"])
def players_set_field():
    import player_db as _db
    data = request.get_json()
    _db.set_player_field(data["username"], data["field"], data.get("value", ""))
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
    ok = pl.create_group(data.get("name", "").strip(), data.get("color", "#888888"), data.get("group_type", "neutral"))
    return jsonify({"ok": ok, "error": "Name already exists." if not ok else None})


@app.route("/players/groups/delete", methods=["POST"])
def players_groups_delete():
    data = request.get_json()
    pl.delete_group(data.get("name", ""))
    return jsonify({"ok": True})


@app.route("/players/groups/update_color", methods=["POST"])
def players_groups_update_color():
    data = request.get_json()
    pl.update_group_color(data.get("name", ""), data.get("color", "#3498db"))
    return jsonify({"ok": True})


@app.route("/players/groups/update_type", methods=["POST"])
def players_groups_update_type():
    data = request.get_json()
    import player_db as _db
    _db.update_group_type(data.get("name", ""), data.get("group_type", "neutral"))
    return jsonify({"ok": True})


@app.route("/players/groups/update_assignment", methods=["POST"])
def players_groups_update_assignment():
    data = request.get_json()
    import player_db as _db
    _db.update_group_assignment(data.get("name", ""), data.get("context", "agg_crimes"), data.get("value", ""))
    return jsonify({"ok": True})


@app.route("/players/groups/rename", methods=["POST"])
def players_groups_rename():
    data = request.get_json()
    import player_db as _db
    ok = _db.rename_group(data.get("old_name", ""), data.get("new_name", "").strip())
    return jsonify({"ok": ok, "error": "Name already exists." if not ok else None})


@app.route("/api/players/group/<group_name>")
def api_players_by_group(group_name):
    import player_db as _db
    return jsonify({"players": _db.get_players_by_group(group_name)})


@app.route("/players/whitelist_bolds", methods=["POST"])
def players_whitelist_bolds():
    import player_db as _db
    BOLD_RANKS = {"Boss", "Don", "Godfather", "Capo di tutti capi"}
    all_players = _db.get_all_players()
    targets = [p["username"] for p in all_players if p.get("rank", "") in BOLD_RANKS]
    already = {p["username"] for p in all_players if p.get("agg_crimes") == "whitelist"}
    newly = [u for u in targets if u not in already]
    if targets:
        _db.bulk_set_assignment(targets, "agg_crimes", "whitelist")
    if newly:
        bot.state.add_log(f"Whitelist bolds: {len(newly)} new — {', '.join(newly)}")
    return jsonify({"ok": True, "count": len(targets), "newly": len(newly), "players": targets})


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

    import player_db as _db
    known = {u.lower(): u for u in _db.get_usernames()}

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
    try:
        opts = bot.request_travel_dests(method, timeout=15.0)
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


@app.route("/restart", methods=["POST"])
def restart():
    import sys
    import threading as _threading
    def _do_restart():
        import time as _time
        bot.stop()
        _time.sleep(2)
        if sys.platform == "win32":
            import subprocess as _sp
            _sp.Popen([sys.executable] + sys.argv)
            os._exit(0)
        else:
            os.execv(sys.executable, [sys.executable] + sys.argv)
    _threading.Thread(target=_do_restart, daemon=True).start()
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
