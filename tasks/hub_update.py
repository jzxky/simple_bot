"""
Hub update — every 10 minutes, report what the bot sees to Player Hub.

Sends the skins JSON unchanged, the bot's current city with that city's active
list, the global online list, and any profile pages the hub asked for on the
previous update. The hub detects births/deaths, career changes, online time
and city presence; this task never decides player state itself.
"""

import time

import browser
import config as cfg
import urls
from tasks.base import Task
from state import GameState

_DEFAULT_INTERVAL_MINUTES = 10
_DEFAULT_PROFILES_PER_UPDATE = 5


def _hub_cfg() -> dict:
    return cfg.load().get("sync", {})


class HubUpdateTask(Task):
    priority = 6
    label = "Hub Update"

    def __init__(self):
        self._last: float = 0.0
        self._profile_requests: list = []
        self._pending_profiles: list = []

    def _interval(self) -> int:
        return max(1, int(_hub_cfg().get("update_interval_minutes", _DEFAULT_INTERVAL_MINUTES))) * 60

    def _enabled(self) -> bool:
        import sync_client
        return bool(sync_client.hub_url()) and _hub_cfg().get("snapshot_enabled", True)

    def can_run(self, state: GameState) -> bool:
        if not self._enabled() or not state.logged_in:
            return False
        return time.monotonic() - self._last >= self._interval()

    def blocked_reasons(self, state):
        reasons = []
        if not self._enabled():
            reasons.append("Hub sync not configured")
        if not state.logged_in:
            reasons.append("Not logged in")
        remaining = self._interval() - (time.monotonic() - self._last)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining // 60)}m)")
        return reasons

    def run(self, state: GameState, executor):
        import players
        import sync_client
        self._last = time.monotonic()

        self._fetch_requested_profiles(state)

        payload = {"observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        raw = players.fetch_skins_raw()
        if raw is not None:
            payload["skins_players"] = raw
            players.download_player_images(raw)
        if state.online_players:
            payload["online_players"] = sorted(state.online_players)
        if state.current_city:
            payload["current_city"] = state.current_city
            payload["city_active"] = sorted(state.local_players)
        if self._pending_profiles:
            payload["profiles"] = self._pending_profiles

        try:
            result = sync_client.send_update(payload)
        except Exception as e:
            state.add_log(f"Hub update failed: {e}")
            return
        self._pending_profiles = []
        self._profile_requests = list(result.get("profile_requests") or [])
        msg = (f"Hub update: {result.get('births', 0)} birth(s), {result.get('deaths', 0)} death(s), "
               f"{result.get('online', 0)} online")
        if result.get("warnings"):
            msg += f" — {'; '.join(result['warnings'])}"
        state.add_log(msg + ".")

    def _fetch_requested_profiles(self, state: GameState):
        """Fetch the profiles the hub asked for last time; they ride the next update."""
        from profile_parser import parse_profile
        if not self._profile_requests or state.in_jail or state.in_hospital:
            return
        limit = max(0, int(_hub_cfg().get("profiles_per_update", _DEFAULT_PROFILES_PER_UPDATE)))
        page = browser.page()
        for name in self._profile_requests[:limit]:
            try:
                resp = page.goto(f"{urls.BASE_URL}/userprofile.asp?username={name}",
                                 wait_until="domcontentloaded", timeout=15000)
                if resp and resp.status == 200:
                    self._pending_profiles.append(parse_profile(page.content(), name))
            except Exception as e:
                state.add_log(f"Hub update: profile fetch failed for {name}: {e}")
        self._profile_requests = []
        try:
            page.goto(urls.BASE_URL + "/main.asp", wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass
