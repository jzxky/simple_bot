"""
war_hub_tasks.py — war checks handed out by Player Hub.

In war server mode the hub decides what this bot checks and how often: the
bot asks the hub for work every `poll_seconds` (set on the hub), does the
checks it gets back, and sends each result to the hub. The hub splits the
work between bots, so two bots don't check the same profile.

Polling and sending run on short-lived background threads so the bot loop
never waits on the network. Against a hub too old to hand out work, the
bot falls back to its own per-check timers (see hub_drives()).
"""

import logging
import threading
import time

import config as cfg
import war_hub_client

log = logging.getLogger(__name__)

_DEFAULT_POLL = 30
_OLD_HUB_RETRY = 600      # seconds before asking an old hub again
_ERROR_RETRY_MIN = 60     # back-off after a network error

_lock = threading.Lock()
_tasks: list = []
_next_poll = 0.0           # monotonic time of the next poll
_poll_seconds = _DEFAULT_POLL
_in_flight = False
_last_ok = 0.0             # monotonic time of the last successful poll
_supported = None          # None until the hub answers; False for an old hub
_last_error = ""


def server_mode() -> bool:
    c = cfg.load()
    wm = c.get("war_mode", {})
    sc = c.get("sync", {})
    return bool(wm.get("mode") == "server"
                and sc.get("enabled") and sc.get("server_url") and sc.get("api_key"))


def checking_on() -> bool:
    wm = cfg.load().get("war_mode", {})
    return bool(wm.get("enabled") and wm.get("checking_enabled") and server_mode())


def hub_drives() -> bool:
    """True while the hub is handing out war checks, so the bot's own
    timer-driven war checks stand down."""
    with _lock:
        if not _supported:
            return False
        fresh = max(180, _poll_seconds * 4)
        return time.monotonic() - _last_ok < fresh


def has_tasks() -> bool:
    with _lock:
        return bool(_tasks)


def take_tasks() -> list:
    with _lock:
        out = list(_tasks)
        _tasks.clear()
        return out


def status() -> dict:
    with _lock:
        return {"supported": _supported, "poll_seconds": _poll_seconds,
                "next_poll_in": max(0, int(_next_poll - time.monotonic())),
                "pending": len(_tasks), "error": _last_error}


def maybe_poll(city: str):
    """Start a background poll if one is due and no work is waiting."""
    global _in_flight
    with _lock:
        if _in_flight or _tasks or time.monotonic() < _next_poll:
            return
        _in_flight = True
    threading.Thread(target=_poll, args=(city,), name="war-hub-poll", daemon=True).start()


def _poll(city: str):
    global _in_flight, _next_poll, _poll_seconds, _last_ok, _supported, _last_error
    try:
        resp = war_hub_client.poll_tasks(city)
    except war_hub_client.HubTooOld:
        with _lock:
            _supported = False
            _last_error = "Hub doesn't hand out war checks yet"
            _next_poll = time.monotonic() + _OLD_HUB_RETRY
            _in_flight = False
        return
    except Exception as e:
        log.warning("war_hub: poll failed: %s", e)
        with _lock:
            _last_error = str(e)
            _next_poll = time.monotonic() + max(_ERROR_RETRY_MIN, _poll_seconds)
            _in_flight = False
        return
    with _lock:
        try:
            _poll_seconds = max(5, int(resp.get("poll_seconds") or _DEFAULT_POLL))
        except (TypeError, ValueError):
            _poll_seconds = _DEFAULT_POLL
        _tasks[:] = [t for t in (resp.get("tasks") or []) if isinstance(t, dict) and t.get("type")]
        _supported = True
        _last_ok = time.monotonic()
        _last_error = ""
        _next_poll = _last_ok + _poll_seconds
        _in_flight = False


def send_result(result: dict):
    """Send a result to the hub without holding up the bot loop."""
    threading.Thread(target=war_hub_client.send_task_result, args=(result,),
                     name="war-hub-result", daemon=True).start()


def reset():
    """Forget queued work and timers (tests, or after leaving server mode)."""
    global _next_poll, _poll_seconds, _in_flight, _last_ok, _supported, _last_error
    with _lock:
        _tasks.clear()
        _next_poll = 0.0
        _poll_seconds = _DEFAULT_POLL
        _in_flight = False
        _last_ok = 0.0
        _supported = None
        _last_error = ""
