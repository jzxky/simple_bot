"""
War checks handed out by Player Hub (war server mode).

Asks the hub for work every poll interval the hub sets, runs each check it
gets back and sends the result to the hub. See war_hub_tasks.py.
"""

import queue

import config as cfg
import war_hub_tasks
from tasks.base import Task, Action
from state import GameState

# Checks that need a page visit, mapped to the executor action that does it.
_ACTIONS = {"ws": "ws_monitor", "jail": "check_jail", "businesses": "scrape_businesses"}


class WarHubChecksTask(Task):
    priority = 20
    label = "War Hub Checks"

    def can_run(self, state: GameState) -> bool:
        if not war_hub_tasks.checking_on() or not state.logged_in:
            return False
        war_hub_tasks.maybe_poll(state.current_city or "")
        return war_hub_tasks.has_tasks()

    def blocked_reasons(self, state):
        reasons = []
        wm = cfg.load().get("war_mode", {})
        if not wm.get("enabled", False):
            reasons.append("War mode disabled")
        if not wm.get("checking_enabled", False):
            reasons.append("Checking disabled")
        if not war_hub_tasks.server_mode():
            reasons.append("Not in server mode")
        if not state.logged_in:
            reasons.append("Not logged in")
        st = war_hub_tasks.status()
        if st["supported"] is False:
            reasons.append("Hub too old, using local timers")
        elif st["error"]:
            reasons.append(f"Hub unreachable: {st['error'][:60]}")
        elif not st["pending"]:
            reasons.append(f"Waiting for hub ({st['next_poll_in']}s)")
        return reasons

    def run(self, state: GameState, executor):
        for task in war_hub_tasks.take_tasks():
            try:
                result = self._run_one(task, state, executor)
            except Exception as e:
                state.add_log(f"War hub check {task.get('type')} failed: {e}")
                continue
            if result:
                war_hub_tasks.send_result(result)

    def _run_one(self, task: dict, state: GameState, executor):
        t = task.get("type")
        if t == "online":
            if not state.current_city:
                return None
            return {"type": "online", "city": state.current_city,
                    "names": list(state.local_players)}
        if t == "home_cities":
            return self._home_cities(task.get("names") or [])
        kind = _ACTIONS.get(t)
        if not kind:
            return None
        q = queue.Queue()
        params = {"result_queue": q}
        if t == "ws":
            names = [n for n in (task.get("names") or []) if n]
            if not names:
                return None
            params["names"] = names
        executor.execute(Action(kind, **params), state)
        try:
            return q.get_nowait()
        except queue.Empty:
            return None  # page didn't load or session expired; the hub re-offers it later

    @staticmethod
    def _home_cities(names: list):
        import player_db
        wanted = {n.lower() for n in names if n}
        if not wanted:
            return None
        cities = [{"name": p["username"], "city": p["homecity"]}
                  for p in player_db.get_all_players()
                  if p["username"].lower() in wanted and p.get("homecity")]
        return {"type": "home_cities", "names": names, "cities": cities}
