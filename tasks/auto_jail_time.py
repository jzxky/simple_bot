import time
import config as cfg
import bot
from tasks.base import Task
from state import GameState


class AutoJailTimeTask(Task):
    priority = 75
    label = "Auto Jail Time"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        mode = jail_cfg.get("auto_jail_time", "off")
        if mode == "off":
            return False
        if state.hold_action_timer:
            return False
        if jail_cfg.get("jailbreak_execute_at", 0) > 0:
            return False
        if mode == "respect_change":
            now = state._estimated_server_time()
            if now is None:
                return False
            minutes_past_midnight = now.hour * 60 + now.minute
            if minutes_past_midnight >= 20:
                return False
        return True

    def run(self, state: GameState, executor):
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        use_warrants = jail_cfg.get("use_warrants", False)
        partner = jail_cfg.get("auto_jail_partner", "")

        target = None

        if use_warrants:
            warrants = bot.request_warrants(timeout=15.0)
            if warrants:
                for w in warrants:
                    if w.get("jail_time"):
                        target = w.get("victim") or w.get("escaper")
                        break

        if not target:
            inmates = bot.request_jail_inmates(timeout=15.0)
            names = (inmates or {}).get("inmates", [])
            if names:
                target = names[0]

        if not target:
            state.add_log("Auto Jail Time: no target found.")
            return

        state.add_log(f"Auto Jail Time: planning jailbreak for {target} (partner: {partner or 'none'}).")
        bot.request_jailbreak_plan(target=target, partner=partner, hold_action_timer=False)

        c["jail"]["jailbreak_execute_at"] = int(time.time()) + 1800
        cfg.save(c)


class AutoJailTimeExecuteTask(Task):
    priority = 76
    label = "Auto Jail Time Execute"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        mode = jail_cfg.get("auto_jail_time", "off")
        if mode == "off":
            return False
        execute_at = jail_cfg.get("jailbreak_execute_at", 0)
        if execute_at <= 0:
            return False
        if mode == "respect_change":
            now = state._estimated_server_time()
            if now is not None:
                minutes_past_midnight = now.hour * 60 + now.minute
                if minutes_past_midnight >= 59:
                    c["jail"]["jailbreak_execute_at"] = 0
                    cfg.save(c)
                    state.add_log("Auto Jail Time: past 12:59am — cancelling pending execute.")
                    return False
        return time.time() >= execute_at

    def run(self, state: GameState, executor):
        c = cfg.load()
        c["jail"]["jailbreak_execute_at"] = 0
        cfg.save(c)
        state.add_log("Auto Jail Time: 30 min elapsed — executing jailbreak.")
        bot.request_jailbreak_execute()
