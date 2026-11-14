"""
Drug trade tasks in their own Chrome window.

Drug house buying and stock checks, dealer contacts and prices, contact buys and
sell offers, smuggling bribes, journal drug trade offers, !middle runs and drug
manufacturing all run on the side browser's "drugs" lane (side_browser.py): a
separate Chrome window on its own profile (.browser_profile_side_drugs) and its
own worker thread, logged in with the main browser's cookies. The main window
stays on whatever it was doing.

Each job opens a fresh tab in that window, runs the executor's handler there on
a copy of the GameState (so the drug pages don't overwrite the main tab's
page_html/current_url), copies the results that matter back (cash, bank,
consumables, jail/hospital, timers) and closes the tab. Jobs on the lane run one
at a time, in the order they were submitted.

While a job is in flight (state.drug_tab_active):
  - the scheduler holds back tasks that travel (changes_city) or move cash
    (moves_cash), so the character doesn't leave the city mid-deal and the money
    withdrawn for a buy isn't deposited straight back
  - drug manufacturing also reserves the action timer
    (state.action_timer_reserved), so no other task submits an action while the
    drug window is about to

Threading: submit() is called on the bot thread (it reads the main browser's
cookies). The job runs on the lane's worker thread and only touches its own tab.
"""

import copy
import threading
import browser
import side_browser
import config as cfg

LANE = "drugs"

# Executor actions the Drugs tab sends (they reply on a result queue).
UI_ACTIONS = {
    "send_blind_eye", "load_drug_contacts", "load_carrying_stock", "load_contact_stock",
    "buy_contact_drugs", "create_drug_offer", "load_drug_house_stock", "buy_drug_house",
    "add_drug_contact", "load_dealer_contacts", "load_contact_prices", "set_contact_prices",
}
# Scheduler-driven drug actions.
TASK_ACTIONS = {"check_drug_trade", "do_middling", "do_drug_manufacturing"}
ACTIONS = UI_ACTIONS | TASK_ACTIONS

# Actions that use the action timer: it is reserved for them while they run.
_ACTION_TIMER_ACTIONS = {"do_drug_manufacturing"}

# Fields copied back from the job's state copy when the job changed them.
_MERGE_FIELDS = ("clean_money", "dirty_money", "bank_balance", "consumables",
                 "in_jail", "jail_release_secs", "in_hospital", "hospital_release_at")
_TIMER_FIELDS = ("timers", "action_timer_ready", "action_timer_end", "agg_pro_active", "agg_pro_end")

_lock = threading.Lock()
_in_flight = 0
_timer_holds = 0


class _Reply:
    """Wraps the UI's reply queue so the job knows whether the handler answered."""

    def __init__(self, q):
        self._q = q
        self.sent = False

    def put(self, item, *args, **kwargs):
        self.sent = True
        self._q.put(item)


def _label(kind: str) -> str:
    return kind.replace("_", " ").capitalize()


def _set_flags(state, delta: int, holds_timer: bool):
    global _in_flight, _timer_holds
    with _lock:
        _in_flight = max(0, _in_flight + delta)
        if holds_timer:
            _timer_holds = max(0, _timer_holds + delta)
        state.drug_tab_active = _in_flight > 0
        state.action_timer_reserved = _timer_holds > 0


def reset(state=None):
    """Forget in-flight jobs (bot start/stop: the lane's queue is gone with it)."""
    global _in_flight, _timer_holds
    with _lock:
        _in_flight = _timer_holds = 0
    if state is not None:
        state.drug_tab_active = False
        state.action_timer_reserved = False


def busy() -> bool:
    with _lock:
        return _in_flight > 0


def submit(state, action, reply_q=None) -> "side_browser.Job":
    """Bot thread: queue `action` (an executor Action whose kind is in ACTIONS)
    to run in the drug window. reply_q, if given, gets the handler's result dict
    (UI requests); a job that fails before replying sends {"ok": False, ...}."""
    holds_timer = action.kind in _ACTION_TIMER_ACTIONS
    reply = None
    if reply_q is not None:
        reply = _Reply(reply_q)
        action.params["result_queue"] = reply
    _set_flags(state, +1, holds_timer)
    headless = cfg.load().get("misc", {}).get("headless", False)
    try:
        return side_browser.submit(
            LANE, action.kind,
            lambda side, job: _run_job(side, job, state, action, reply, holds_timer),
            cookies=browser.export_cookies(), headless=headless,
        )
    except Exception:
        _set_flags(state, -1, holds_timer)
        raise


def _shadow_state(state):
    shadow = copy.copy(state)
    shadow.add_log = lambda msg: state.add_log(f"[Drug window] {msg}")
    shadow.push_notification = state.push_notification
    # The reservation is for everyone except the drug window itself.
    shadow.action_timer_reserved = False
    return shadow


def _merge_back(state, shadow, before: dict):
    if not shadow.logged_in:
        return  # the drug tab saw the login page — its figures aren't the character's
    for f in _MERGE_FIELDS:
        if getattr(shadow, f) != before[f]:
            setattr(state, f, getattr(shadow, f))
    if shadow.timers and any(getattr(shadow, f) != before[f] for f in _TIMER_FIELDS):
        for f in _TIMER_FIELDS:
            setattr(state, f, getattr(shadow, f))


def _run_job(side, job, state, action, reply, holds_timer: bool):
    """Worker thread."""
    import executor
    label = _label(action.kind)
    shadow = _shadow_state(state)
    before = {f: getattr(shadow, f) for f in _MERGE_FIELDS + _TIMER_FIELDS}
    pg = None
    try:
        if job.cancel.is_set():
            raise RuntimeError(job.cancel_reason or "cancelled")
        handler = executor.HANDLERS[action.kind]
        pg = side.new_page(job)
        with browser.use_page(pg):
            handler(action, shadow)
    except Exception as e:
        state.add_log(f"[Drug window] {label} error — {e}")
        if reply is not None and not reply.sent:
            reply.put({"ok": False, "message": f"Drug window error: {e}"})
        if browser.is_lost_error(e):
            raise  # the lane tears its browser down; the next job relaunches it
    finally:
        if pg is not None:
            side.close_page(pg)
        try:
            _merge_back(state, shadow, before)
        finally:
            if reply is not None and not reply.sent:
                reply.put({"ok": False, "message": "The request finished without a result — see the log."})
            _set_flags(state, -1, holds_timer)
