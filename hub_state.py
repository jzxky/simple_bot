"""
hub_state.py — The bot's game status, as shown on Player Hub's Remote page.

snapshot() picks the values the owner chose for the hub (card and details;
see the "Bot status on the hub's Remote page" doc). Times are sent as
seconds left at the moment of sending, so the hub can count down without
knowing the game's clock. Game credentials are not part of GameState and
never appear here.
"""

import time


def _secs_until(end, now_server) -> "int | None":
    if end is None or now_server is None:
        return None
    return max(0, int((end - now_server).total_seconds()))


def _epoch_left(t) -> "int | None":
    return None if t is None else max(0, int(t - time.time()))


def snapshot() -> dict:
    import bot
    s = bot.state
    now = s._estimated_server_time()
    running = bot.is_running()

    def timer(name):
        t = (s.timers or {}).get(name) or {}
        if t.get("ready"):
            return 0
        return _secs_until(t.get("end"), now)

    action_left = 0 if s.action_available() else _secs_until(s.action_timer_end, now)
    card = {
        "name": s.own_name, "rank": s.rank, "next_rank": s.next_rank, "rank_progress": s.rank_progress,
        "occupation": s.occupation, "home_city": s.home_city, "city": s.current_city,
        "dead": bool(s.character_dead), "energy": s.energy,
        "in_hospital": bool(s.in_hospital), "hospital_left": _epoch_left(s.hospital_release_at),
        "clean_money": s.clean_money, "dirty_money": s.dirty_money,
        "action_left": action_left,
        "agg_pro": bool(s.agg_pro_active), "agg_pro_left": timer("aggpro") if s.agg_pro_active else None,
        "in_jail": bool(s.in_jail), "jail_left": s.jail_release_secs if s.in_jail else None,
        "running": running, "paused": bool(running and bot.is_paused()),
        "task": s.current_task, "error": s.last_error,
    }
    details = {
        "health": s.health, "vehicle_health": s.vehicle_health, "bank": s.bank_balance,
        "earns_24h": s.earns_24h, "consumables_24h": s.consumables_24h,
        "consumables": dict(s.consumables or {}), "jail_consumables": dict(s.jail_consumables or {}),
        "timers": {n: timer(n) for n in sorted(s.timers or {})},
        "flight_left": _epoch_left(s.flight_departs_at),
        "jail_rank": s.jail_rank, "cs_owed": s.cs_sentence,
        "timer_held": bool(s.hold_action_timer), "auto_jail_hold": bool(s.auto_jail_hold),
        "logged_in": bool(s.logged_in),
        "agg_tab": s.agg_tab_crime if s.agg_tab_active else "",
        "snipe": bool(s.snipe_active), "drug_store_tab": bool(s.drug_store_tab_active),
        "agg_fails_30m": s.agg_fail_count(),
        "server_time": now.strftime("%H:%M:%S") if now else "",
        "page": (s.current_url or "").split("?")[0].rsplit("/", 1)[-1],
        "online": len(s.online_players or ()), "same_city": len(s.local_players or ()),
        "skills": sorted(s.available_skills or ()),
        "lawyer_cases": {c: len(v) if isinstance(v, (list, tuple, set, dict)) else v
                         for c, v in (s.lawyer_cases_by_city or {}).items()},
    }
    return {"card": card, "details": details}
