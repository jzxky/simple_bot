"""
Once a day, walk the recent obituaries (players who died in the last 3 days) and
save a character history snapshot for each via playerstatsalive.asp, for later
viewing. Logs each successfully saved entry.
"""

import time
from datetime import datetime, timezone, timedelta

import config as cfg
import character_history as ch
import player_db as pdb
from tasks.base import Task, Action
from state import GameState

_DAY = 24 * 3600
_OBIT_WINDOW_DAYS = 3


class ObituaryHistoryTask(Task):
    priority = 8  # low; below the live character-history task
    label = "Obituary History"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        c = cfg.load().get("character_history", {})
        if not c.get("enabled", False):
            return False
        # Last-run time is persisted in config so a restart doesn't re-trigger it.
        return time.time() - float(c.get("obituary_last_run", 0) or 0) >= _DAY

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        c = cfg.load().get("character_history", {})
        if not c.get("enabled", False):
            reasons.append("Not enabled")
        elapsed = time.time() - float(c.get("obituary_last_run", 0) or 0)
        if elapsed < _DAY:
            remaining = (_DAY - elapsed) / 3600
            reasons.append(f"Cooldown ({int(remaining)}h)")
        return reasons

    def run(self, state: GameState, executor):
        c = cfg.load()
        c.setdefault("character_history", {})["obituary_last_run"] = int(time.time())
        cfg.save(c)

        cutoff = datetime.now(timezone.utc) - timedelta(days=_OBIT_WINDOW_DAYS)
        names = []
        for p in pdb.get_all_players():
            if p.get("active"):
                continue
            died = p.get("died_at")
            if not died:
                continue
            try:
                dt = datetime.strptime(died, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except Exception:
                continue
            if dt < cutoff:
                continue
            # Skip players that already have a saved history file.
            if ch.has_saved(p["username"]):
                continue
            names.append(p["username"])

        if not names:
            return

        state.add_log(f"Obituary history: scanning {len(names)} recent obituary entry(ies).")
        saved = 0
        for name in names:
            try:
                if ch.fetch_and_save(name, alive_lookup=True):
                    saved += 1
                    state.add_log(f"Obituary history: saved {name}.")
            except Exception as e:
                state.add_log(f"Obituary history: {name} failed ({e}).")

        state.add_log(f"Obituary history: saved {saved}/{len(names)}.")
        # Restore browser/state to a known page after the scan.
        executor.execute(Action("refresh_state"), state)
