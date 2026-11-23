"""
Drug trade tasks in their own Chrome window.

Drug house buying and stock checks, dealer contacts and prices, contact buys and
sell offers, smuggling bribes, journal drug trade offers and !middle runs all run
on the side browser's "drugs" lane (side_browser.py): a
separate Chrome window (throwaway profile) and its
own worker thread, logged in with the main browser's cookies. The main window
stays on whatever it was doing. Drug manufacturing (an action-timer action) and
the Auckland drug store (its own tab, drug_store.py) are not drug trade tasks
and stay where they were.

Each job opens a fresh tab in that window, runs the executor's handler there on
a copy of the GameState (so the drug pages don't overwrite the main tab's
page_html/current_url), copies the results that matter back (cash, bank,
consumables, jail/hospital, timers) and closes the tab. Jobs on the lane run one
at a time, in the order they were submitted.

While a job is in flight (state.drug_tab_active) the scheduler holds back tasks
that travel (changes_city) or move cash (moves_cash), so the character doesn't
leave the city mid-deal and the money withdrawn for a buy isn't deposited
straight back.

Threading: submit() is called on the bot thread (it reads the main browser's
cookies). The job runs on the lane's worker thread and only touches its own tab.
"""

import copy
import threading
import time
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
TASK_ACTIONS = {"check_drug_trade", "do_middling", "middle_notify"}
ACTIONS = UI_ACTIONS | TASK_ACTIONS


# Fields copied back from the job's state copy when the job changed them.
_MERGE_FIELDS = ("clean_money", "dirty_money", "bank_balance", "consumables",
                 "in_jail", "jail_release_secs", "in_hospital", "hospital_release_at")
_TIMER_FIELDS = ("timers", "action_timer_ready", "action_timer_end", "agg_pro_active", "agg_pro_end")

_lock = threading.Lock()
_in_flight = 0
# When a job last found the drug window logged out. Jobs queued before then
# carry the same (stale) cookies and would only fail the same way, one
# "Session expired" line each — they're skipped instead. Jobs submitted
# later bring fresh cookies from the main browser.
_logged_out_at = 0.0


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


def _set_flags(state, delta: int):
    global _in_flight
    with _lock:
        _in_flight = max(0, _in_flight + delta)
        state.drug_tab_active = _in_flight > 0


def reset(state=None):
    """Forget in-flight jobs (bot start/stop: the lane's queue is gone with it)."""
    global _in_flight
    with _lock:
        _in_flight = 0
    if state is not None:
        state.drug_tab_active = False


def busy() -> bool:
    with _lock:
        return _in_flight > 0


def submit(state, action, reply_q=None) -> "side_browser.Job":
    """Bot thread: queue `action` (an executor Action whose kind is in ACTIONS)
    to run in the drug window. reply_q, if given, gets the handler's result dict
    (UI requests); a job that fails before replying sends {"ok": False, ...}."""
    reply = None
    if reply_q is not None:
        reply = _Reply(reply_q)
        action.params["result_queue"] = reply
    _set_flags(state, +1)
    submitted_at = time.time()
    headless = cfg.load().get("misc", {}).get("headless", False)
    try:
        return side_browser.submit(
            LANE, action.kind,
            lambda side, job: _run_job(side, job, state, action, reply, submitted_at),
            cookies=browser.export_cookies(), headless=headless,
        )
    except Exception:
        _set_flags(state, -1)
        raise


def _shadow_state(state):
    shadow = copy.copy(state)
    shadow.add_log = lambda msg: state.add_log(f"[Drug window] {msg}")
    shadow.push_notification = state.push_notification
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


def _run_job(side, job, state, action, reply, submitted_at=None):
    """Worker thread."""
    global _logged_out_at
    import executor
    label = _label(action.kind)
    if submitted_at is not None and submitted_at <= _logged_out_at:
        try:
            if reply is not None:
                reply.put({"ok": False, "message": "The drug window was logged out — try again."})
        finally:
            _set_flags(state, -1)
        return
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
        if not shadow.logged_in and state.logged_in:
            _logged_out_at = time.time()
            queued = side_browser.queued(LANE)
            if queued:
                state.add_log(f"[Drug window] Logged out — skipping the {queued} drug "
                              f"job(s) queued behind this one.")
        try:
            _merge_back(state, shadow, before)
        finally:
            if reply is not None and not reply.sent:
                reply.put({"ok": False, "message": "The request finished without a result — see the log."})
            _set_flags(state, -1)
