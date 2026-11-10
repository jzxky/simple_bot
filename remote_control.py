"""
remote_control.py — Let Player Hub users control this bot without port forwarding.

When Settings → Remote control is on, a few worker threads long-poll the hub
(sync.server_url, authenticated with sync.api_key) for requests from hub users.
Each request is replayed against this bot's own Flask control panel in-process
and the answer posted back. Nothing listens for inbound connections.

The hub only relays once an admin has approved this bot and assigned it to
users. Requests that arrive this way are marked in the WSGI environ
(REMOTE_ENVIRON_KEY), and the control panel refuses the things that must stay
local: game credentials, the PIN, sync/remote settings and shutdown.

Only turned on or off from this machine's own control panel.
"""

import base64
import ipaddress
import json
import logging
import os
import threading
import time
import uuid
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import config as cfg

log = logging.getLogger(__name__)

REMOTE_ENVIRON_KEY = "simple_bot.remote_user"
WORKERS = 3
POLL_TIMEOUT = 40          # hub holds a poll ~20 s; allow for slow links
IDLE_RECHECK = 5           # seconds between config checks while off
NOT_APPROVED_WAIT = 15     # seconds between polls while pending/blocked

_lock = threading.Lock()
_state = {"status": "off", "detail": ""}
_started = False
_wake = threading.Event()
# New on every start, so the hub can tell a restarted bot from a slow one.
_SESSION = uuid.uuid4().hex


def _version() -> str:
    try:
        import paths
        with open(os.path.join(paths.resource_dir(), "VERSION")) as f:
            return f.read().strip()
    except Exception:
        return ""


def _set(status: str, detail: str = ""):
    with _lock:
        _state["status"] = status
        _state["detail"] = detail


def status() -> dict:
    """{"status": off|connecting|pending|approved|blocked|error, "detail": str}"""
    with _lock:
        st = dict(_state)
    if st["status"] == "off" and cfg.load().get("remote", {}).get("enabled", False):
        st["status"] = "connecting"
    return st


def url_allowed(url: str) -> bool:
    """HTTPS, or plain HTTP only to a private / loopback address."""
    parts = urlsplit(url or "")
    if parts.scheme == "https":
        return True
    if parts.scheme != "http" or not parts.hostname:
        return False
    host = parts.hostname
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def settings():
    """(server_url, api_key) when remote control should run, else None with a reason."""
    c = cfg.load()
    if not c.get("remote", {}).get("enabled", False):
        return None, ""
    sync = c.get("sync", {})
    url = (sync.get("server_url") or "").strip().rstrip("/")
    key = (sync.get("api_key") or "").strip()
    if not url or not key:
        return None, "Set the Player Hub server URL and API key under Sync."
    if not url_allowed(url):
        return None, "The Player Hub URL must use https:// (plain http is only allowed on a local network)."
    return (url, key), ""


def _post(url: str, key: str, path: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url + path, data=json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def handle(frame: dict) -> dict:
    """Replay one relayed request against the local control panel."""
    from ui.app import app
    rid = frame.get("id")
    try:
        body = base64.b64decode(frame.get("body") or "")
        with app.test_client() as c:
            r = c.open(path=frame.get("path") or "/", method=frame.get("method") or "GET",
                       headers=frame.get("headers") or {}, data=body,
                       environ_overrides={REMOTE_ENVIRON_KEY: frame.get("user") or "hub"})
            data = r.get_data()
            headers = {k: v for k, v in r.headers.items() if k.lower() != "set-cookie"}
            status = r.status_code
            r.close()
    except Exception as e:
        log.exception("Remote request failed: %s %s", frame.get("method"), frame.get("path"))
        data, headers, status = f"Bot error: {e}".encode(), {"Content-Type": "text/plain"}, 500
    return {"id": rid, "status": status, "headers": headers, "body": base64.b64encode(data).decode()}


def _worker(n: int):
    backoff = 5
    while True:
        target, reason = settings()
        if not target:
            if n == 0:
                _set("error" if reason else "off", reason)
            _wake.wait(IDLE_RECHECK)
            _wake.clear()
            continue
        url, key = target
        try:
            d = _post(url, key, "/api/remote/poll", {"version": _version(), "session": _SESSION}, POLL_TIMEOUT)
        except urllib.error.HTTPError as e:
            msg = "The hub rejected this bot's API key." if e.code == 401 else \
                  "The hub doesn't support remote control yet." if e.code == 404 else f"Hub error {e.code}."
            _set("error", msg)
            time.sleep(30)
            continue
        except Exception as e:
            _set("error", f"Can't reach the hub ({e.__class__.__name__}).")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        backoff = 5
        st = d.get("status", "")
        if st != "approved":
            _set(st or "error", "")
            time.sleep(NOT_APPROVED_WAIT + n * 3)
            continue
        _set("approved", "")
        for frame in d.get("requests") or []:
            resp = handle(frame)
            try:
                _post(url, key, "/api/remote/respond", resp, 30)
            except Exception as e:
                log.warning("Remote respond failed: %s", e)


def _say_goodbye_when_disabled():
    """Tell the hub straight away when remote control is switched off here."""
    last = None
    while True:
        target, _ = settings()
        if last and not target:
            try:
                _post(last[0], last[1], "/api/remote/bye", {}, 10)
            except Exception:
                pass
        last = target
        time.sleep(IDLE_RECHECK)


def start():
    """Start the background threads (idempotent). They idle while the setting is off."""
    global _started
    with _lock:
        if _started:
            return
        _started = True
    for n in range(WORKERS):
        threading.Thread(target=_worker, args=(n,), name=f"remote-{n}", daemon=True).start()
    threading.Thread(target=_say_goodbye_when_disabled, name="remote-bye", daemon=True).start()


def nudge():
    """Settings changed: re-check now instead of after the idle wait."""
    _wake.set()
