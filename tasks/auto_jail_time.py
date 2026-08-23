import queue
import time
import config as cfg
import bot
from tasks.base import Task, Action
from state import GameState

_WARRANT_CHECK_INTERVAL = 1800  # seconds between warrant checks
_JAIL_CHECK_INTERVAL = 1800     # seconds between jail.asp roster checks

# Accounts that can show up in name lists but can never actually be jailed
# (e.g. "Administrator" has appeared tagged with the online-list "jail" CSS
# class without genuinely being in jail).
_NON_TARGETABLE = {"administrator"}


def _real_inmates(names) -> list:
    return [n for n in names if n and n.strip().lower() not in _NON_TARGETABLE]


# Respect-change timing (server time). The respect changeover is 01:00.
# We start looking for a break at 22:30, and once one is planned we visit
# jailbreak.asp 31 minutes later (the break needs ~30 min to mature — visiting
# earlier is too soon).
_PLAN_START_MIN       = 22 * 60 + 30   # 22:30 — plan window opens
_CHANGEOVER_MIN       = 60             # 01:00 — respect change; plan window closes
_EXECUTE_DELAY        = 31 * 60        # visit jailbreak.asp 31 min after planning
_EXECUTE_DEADLINE_MIN = 2 * 60         # 02:00 — abandon an unfired execute past here


def _server_mins(state) -> "int | None":
    """Minutes past server midnight, or None if server time is unknown."""
    now = state._estimated_server_time()
    if now is None:
        return None
    return now.hour * 60 + now.minute


def _in_plan_window(t: int) -> bool:
    """22:30 → 01:00, wrapping midnight."""
    return t >= _PLAN_START_MIN or t < _CHANGEOVER_MIN


def _past_execute_deadline(t: int) -> bool:
    """From 02:00 up to the next plan window (22:30) — a pending execute is stale."""
    return _EXECUTE_DEADLINE_MIN <= t < _PLAN_START_MIN


def _after_changeover(t: int) -> bool:
    """01:00 → 22:30 — the respect change has passed and the plan window hasn't
    reopened yet. Consumables may be restored any time in here."""
    return _CHANGEOVER_MIN <= t < _PLAN_START_MIN


class AutoJailTimeTask(Task):
    priority = 75
    label = "Auto Jail Time"

    def __init__(self):
        self._last_warrant_check: float = 0.0
        self._last_jail_check: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        mode = jail_cfg.get("auto_jail_time", "off")
        if mode == "off":
            return False
        # A partner is required to plan a jail break.
        if not jail_cfg.get("auto_jail_partner", "").strip():
            return False
        if state.hold_action_timer:
            return False
        # Non-gangsters can only plan a jail break in their home city.
        if "gangster" not in (state.occupation or "").lower() and not state.in_home_city():
            return False
        # Planning consumes the action timer — wait until it's free. Priority 75
        # (above the 50–60 action-timer tasks) ensures it runs first once free.
        if not state.action_available():
            return False
        if jail_cfg.get("jailbreak_execute_at", 0) > 0:
            return False
        if mode == "respect_change":
            t = _server_mins(state)
            if t is None or not _in_plan_window(t):
                return False
        use_warrants = jail_cfg.get("use_warrants", False)
        if use_warrants:
            # Rate-limit warrant checks to every 30 minutes
            return time.time() - self._last_warrant_check >= _WARRANT_CHECK_INTERVAL
        else:
            # Run if there are local jail targets visible on the current page,
            # or periodically to check the authoritative jail.asp roster instead.
            pop = bot.online_population()
            if pop.get("jail_inmates"):
                return True
            return time.time() - self._last_jail_check >= _JAIL_CHECK_INTERVAL

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        mode = jail_cfg.get("auto_jail_time", "off")
        if mode == "off":
            reasons.append("Not enabled")
            return reasons
        if not jail_cfg.get("auto_jail_partner", "").strip():
            reasons.append("No partner set")
        if state.hold_action_timer:
            reasons.append("Action timer held")
        if "gangster" not in (state.occupation or "").lower() and not state.in_home_city():
            reasons.append("Not in home city (non-gangster)")
        if not state.action_available():
            reasons.append("Action timer busy")
        if jail_cfg.get("jailbreak_execute_at", 0) > 0:
            reasons.append("Execute pending")
        if mode == "respect_change":
            t = _server_mins(state)
            if t is None or not _in_plan_window(t):
                reasons.append("Outside plan window")
        use_warrants = jail_cfg.get("use_warrants", False)
        if use_warrants:
            if time.time() - self._last_warrant_check < _WARRANT_CHECK_INTERVAL:
                remaining = _WARRANT_CHECK_INTERVAL - (time.time() - self._last_warrant_check)
                reasons.append(f"Warrant check cooldown ({int(remaining // 60)}m)")
        else:
            pop = bot.online_population()
            if not pop.get("jail_inmates"):
                remaining = _JAIL_CHECK_INTERVAL - (time.time() - self._last_jail_check)
                if remaining > 0:
                    reasons.append(f"No jail inmates online (jail.asp recheck in {int(remaining // 60)}m)")
                else:
                    reasons.append("No jail inmates online (jail.asp recheck due)")
        return reasons

    def run(self, state: GameState, executor):
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        mode = jail_cfg.get("auto_jail_time", "off")
        use_warrants = jail_cfg.get("use_warrants", False)
        partner = jail_cfg.get("auto_jail_partner", "")

        target = None

        if use_warrants:
            self._last_warrant_check = time.time()
            result_q = queue.Queue()
            executor.execute(Action("check_warrants", result_queue=result_q), state)
            try:
                warrants = result_q.get(timeout=30)
                for w in warrants:
                    if w.get("jail_time"):
                        target = w.get("victim") or w.get("escaper")
                        break
            except queue.Empty:
                state.add_log("Auto Jail Time: warrants check timed out.")

        if not target:
            pop = bot.online_population()
            names = _real_inmates(pop.get("jail_inmates", []))
            if names:
                target = names[0]

        if not target:
            # Authoritative fallback — the online list only reflects who's
            # currently shown on the current page; jail.asp is the real roster.
            self._last_jail_check = time.time()
            try:
                result = bot._fetch_jail_inmates()
                names = _real_inmates(result.get("inmates", []))
                if names:
                    target = names[0]
            except Exception as e:
                state.add_log(f"Auto Jail Time: jail.asp lookup failed: {e}")

        if not target:
            state.add_log("Auto Jail Time: no target found.")
            return

        state.add_log(f"Auto Jail Time: planning jailbreak for {target} (partner: {partner or 'none'}).")
        bot.request_jailbreak_plan(target=target, partner=partner, hold_action_timer=False)

        # In respect_change mode, keep the character jailed through the change by
        # turning off jail 'use consumables' (contraband shortens the sentence).
        # Only do so if it was on, and flag it so it can be auto-restored once the
        # change has passed. Reflected in open settings tabs via the rev bump.
        if mode == "respect_change" and c["jail"].get("use_consumables", False):
            c["jail"]["use_consumables"] = False
            c["jail"]["consumables_auto_off"] = True
            state.add_log("Auto Jail Time: jail 'use consumables' disabled while a break is planned.")

        c["jail"]["jailbreak_execute_at"] = int(time.time()) + _EXECUTE_DELAY
        cfg.save(c)
        import settings_rev
        settings_rev.bump()


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
            t = _server_mins(state)
            if t is not None and _past_execute_deadline(t):
                c["jail"]["jailbreak_execute_at"] = 0
                cfg.save(c)
                state.add_log("Auto Jail Time: past the execute window — cancelling pending execute.")
                return False
        return time.time() >= execute_at

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        mode = jail_cfg.get("auto_jail_time", "off")
        if mode == "off":
            reasons.append("Not enabled")
        execute_at = jail_cfg.get("jailbreak_execute_at", 0)
        if execute_at <= 0:
            reasons.append("No execute pending")
        elif time.time() < execute_at:
            remaining = execute_at - time.time()
            reasons.append(f"Execute wait ({int(remaining // 60)}m)")
        return reasons

    def run(self, state: GameState, executor):
        c = cfg.load()
        c["jail"]["jailbreak_execute_at"] = 0
        cfg.save(c)
        # After the 31-minute wait the bot only needs to visit the jailbreak page;
        # actually executing the break is not required.
        state.add_log("Auto Jail Time: 31 min elapsed — visiting jailbreak page.")
        executor.execute(Action("navigate", url="/income/jailbreak.asp"), state)


class AutoJailConsumablesRestoreTask(Task):
    """Re-enables jail 'use consumables' after respect_change auto-disabled it.

    Once the respect change (01:00) has passed, the protection is no longer
    needed — shortening any later sentence is fine — so consumables may be
    restored any time after 01:00 (while not currently in jail and with no visit
    still pending)."""
    priority = 77
    label = "Auto Jail Consumables Restore"

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        if not jail_cfg.get("consumables_auto_off", False):
            return False
        if jail_cfg.get("jailbreak_execute_at", 0) > 0:
            return False  # still waiting to visit / not yet jailed
        t = _server_mins(state)
        return t is not None and _after_changeover(t)

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        c = cfg.load()
        jail_cfg = c.get("jail", {})
        if not jail_cfg.get("consumables_auto_off", False):
            reasons.append("No auto-off flag")
        if jail_cfg.get("jailbreak_execute_at", 0) > 0:
            reasons.append("Execute pending")
        t = _server_mins(state)
        if t is None:
            reasons.append("Server time unknown")
        elif not _after_changeover(t):
            reasons.append("Before changeover")
        return reasons

    def run(self, state: GameState, executor):
        c = cfg.load()
        c["jail"]["use_consumables"] = True
        c["jail"]["consumables_auto_off"] = False
        cfg.save(c)
        import settings_rev
        settings_rev.bump()
        state.add_log("Auto Jail Time: respect change passed — jail 'use consumables' re-enabled.")
