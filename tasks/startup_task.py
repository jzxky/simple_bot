"""
Bundles first-login housekeeping into a single scheduler tick:
earn catalog refresh, earn queue check, and player list refresh.
"""

import time
from tasks.base import Task, Action
from state import GameState


class StartupTask(Task):
    priority = 89
    label = "Startup Bundle"

    def __init__(self, earns_task=None, char_history_task=None, player_refresh_task=None):
        self._done = False
        self._earns_task = earns_task
        self._char_history_task = char_history_task
        self._player_refresh_task = player_refresh_task

    def can_run(self, state: GameState) -> bool:
        return not self._done and state.logged_in and not state.in_jail

    def blocked_reasons(self, state):
        reasons = []
        if self._done:
            reasons.append("Already completed")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        return reasons

    @staticmethod
    def _drug_manufacturing_configured() -> bool:
        import config as cfg
        c = cfg.load()
        act, away = c.get("action", {}), c.get("away_action", {})
        return ((act.get("enabled") and act.get("type") == "drug_manufacturing")
                or (away.get("enabled") and away.get("type") == "drug_manufacturing"))

    def run(self, state: GameState, executor):
        self._done = True

        # check_earns re-scrapes the earn catalog itself (via _scrape_earn_catalog),
        # so a separate refresh_earn_catalog call here would just visit earn.asp twice.
        # _earns_task is only set when earns is enabled in auto mode (see bot.py),
        # so this also skips the catalog refresh/queue-fill when earns is disabled.
        if self._earns_task is not None:
            state.add_log("Startup: checking earn queue.")
            try:
                import config as cfg
                earn_type = cfg.load().get("earns", {}).get("earn_type", "surgeon")
                executor.execute(Action("check_earns", earn_type=earn_type), state)
            except Exception as e:
                state.add_log(f"Startup earn queue check failed: {e}")

        elif self._drug_manufacturing_configured():
            # Drug manufacturing needs the Mortician Assistant earn unlocked,
            # which is read from the earn catalog — refresh it even with earns off.
            state.add_log("Startup: refreshing earns list (drug manufacturing check).")
            try:
                executor.execute(Action("refresh_earn_catalog"), state)
            except Exception as e:
                state.add_log(f"Startup earn list refresh failed: {e}")

        state.add_log("Startup: refreshing player list.")
        try:
            import sync_client
            if sync_client.hub_managed():
                r = sync_client.mirror_from_hub()
                state.add_log(f"Startup: player list mirrored from Player Hub ({r['players']} player(s)).")
            else:
                from players import _refresh_impl
                count, marked = _refresh_impl()
                msg = f"Startup: player list refreshed: {count} active players."
                if marked:
                    msg += f" Marked {marked} absent player(s) as dead."
                state.add_log(msg)
        except Exception as e:
            state.add_log(f"Startup player refresh failed: {e}")

        now = time.monotonic()
        if self._earns_task and hasattr(self._earns_task, "_last_fired"):
            self._earns_task._last_fired = now
        if self._char_history_task and hasattr(self._char_history_task, "_last_run"):
            self._char_history_task._last_run = time.time()
        if self._player_refresh_task and hasattr(self._player_refresh_task, "_last_run"):
            self._player_refresh_task._last_run = now
