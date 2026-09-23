"""
Home city reporter for war mode (server mode).

Periodically reads war target home cities from the local player database
and reports them to the Player Hub. Ties into the normal player list DB
checks — no extra navigation needed since the player DB is already
populated by the scrape_players flow.
"""

import time

import config as cfg
from tasks.base import Task
from state import GameState


class HomeCityCheckTask(Task):
    priority = 4
    label = "Home City Check"

    def __init__(self):
        self._last: float = 0.0

    def _is_server_mode(self) -> bool:
        c = cfg.load()
        wm = c.get("war_mode", {})
        sc = c.get("sync", {})
        return (wm.get("mode") == "server"
                and sc.get("enabled") and sc.get("server_url") and sc.get("api_key"))

    def _interval(self) -> int:
        wm = cfg.load().get("war_mode", {})
        return max(1, int(wm.get("home_city_check_interval_minutes", 5) or 5)) * 60

    def can_run(self, state: GameState) -> bool:
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            return False
        if not wm.get("checking_enabled", False):
            return False
        if not self._is_server_mode():
            return False
        if not state.logged_in:
            return False
        return time.monotonic() - self._last >= self._interval()

    def blocked_reasons(self, state):
        reasons = []
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            reasons.append("War mode disabled")
        if not wm.get("checking_enabled", False):
            reasons.append("Checking disabled")
        if not self._is_server_mode():
            reasons.append("Not in server mode")
        if not state.logged_in:
            reasons.append("Not logged in")
        remaining = self._interval() - (time.monotonic() - self._last)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining // 60)}m)")
        return reasons

    def run(self, state: GameState, executor):
        import war_mode
        import war_hub_client
        import player_db
        self._last = time.monotonic()
        pairs = war_mode.all_names_from_hub()
        if not pairs:
            return
        target_names = {name.lower() for _, name in pairs}
        all_players = player_db.get_all_players()
        cities = []
        for p in all_players:
            if p["username"].lower() in target_names and p.get("homecity"):
                cities.append({"name": p["username"], "city": p["homecity"]})
        if cities:
            war_hub_client.report_home_cities(cities)
            state.add_log(f"Home city check: reported {len(cities)} target(s).")
