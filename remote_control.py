"""
remote_control.py — Let Player Hub users control this bot without port forwarding.

When Settings → Remote control is on, a few worker threads long-poll the hub
(sync.server_url, authenticated with sync.api_key) for requests from hub users.
Each request is replayed against this bot's own Flask control panel in-process
and the answer posted back. Nothing listens for inbound connections.

Pairing is self-service: "Pair with hub" shows a one-time code here (and sends
it with the polls); the owner types it on the hub's Remote page, which links
this bot to their hub account. Only the owner and people they share it with
can open it; hub admins get no access. "Unpair" here cuts every hub user off.

Requests that arrive this way are marked in the WSGI environ
(REMOTE_ENVIRON_KEY), and the control panel refuses the things that must stay
local: game credentials, the PIN, sync/remote settings and shutdown.

Only turned on or off from this machine's own control panel. The same goes
for "Allow plugins from the hub" (see plugin_sync.py).
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

import action_log
import config as cfg
import hub_errors
import hub_state
import plugin_sync

log = logging.getLogger(__name__)

REMOTE_ENVIRON_KEY = "simple_bot.remote_user"
REMOTE_SID_ENVIRON_KEY = "simple_bot.remote_sid"
UNLOCK_IDLE = 12 * 3600    # remote password stays entered this long without use
MAX_FAILS = 5              # wrong remote passwords before a lockout
LOCKOUT = 300              # seconds
WORKERS = 3
POLL_TIMEOUT = 40          # hub holds a poll ~20 s; allow for slow links
IDLE_RECHECK = 5           # seconds between config checks while off
UNPAIRED_WAIT = 15         # seconds between polls while no hub user is paired
PAIRING_WAIT = 3           # ... while a pairing code is showing
PAIR_CODE_TTL = 600
STATE_EVERY = 5             # seconds between game status checks
STATE_HEARTBEAT = 60        # resend unchanged status this often
FEED_EVERY = 5              # seconds between action history uploads
FEED_BATCH = 200
FEED_BACKFILL = 200         # recent actions sent when the hub has none from this bot
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I

_lock = threading.Lock()
_state = {"status": "off", "detail": "", "owner": "", "shared": 0}
_pairing = {"code": "", "expires": 0.0}
_unpair_requested = False
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


def _set(status: str, detail: str = "", **extra):
    with _lock:
        _state["status"] = status
        _state["detail"] = detail
        _state.update(extra)


def _active_code() -> str:
    with _lock:
        if _pairing["code"] and _pairing["expires"] > time.time():
            return _pairing["code"]
        _pairing["code"] = ""
        return ""


def start_pairing() -> dict:
    """Show a new one-time code; the hub accepts it while this bot keeps sending it."""
    import secrets
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    with _lock:
        _pairing["code"] = code
        _pairing["expires"] = time.time() + PAIR_CODE_TTL
    nudge()
    return pairing()


def cancel_pairing():
    with _lock:
        _pairing["code"] = ""


def pairing() -> dict:
    code = _active_code()
    return {"code": f"{code[:4]}-{code[4:]}" if code else "",
            "expires_in": max(0, int(_pairing["expires"] - time.time())) if code else 0}


def request_unpair():
    """Cut every hub user off on the next poll."""
    global _unpair_requested
    with _lock:
        _unpair_requested = True
    cancel_pairing()
    nudge()


def status() -> dict:
    """{"status": off|connecting|paired|unpaired|error, "detail", "owner", "shared"}"""
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
                       environ_overrides={REMOTE_ENVIRON_KEY: frame.get("user") or "hub",
                                          REMOTE_SID_ENVIRON_KEY: frame.get("rsid") or ""})
            data = r.get_data()
            headers = {k: v for k, v in r.headers.items() if k.lower() != "set-cookie"}
            status = r.status_code
            r.close()
    except Exception as e:
        log.exception("Remote request failed: %s %s", frame.get("method"), frame.get("path"))
        data, headers, status = f"Bot error: {e}".encode(), {"Content-Type": "text/plain"}, 500
    return {"id": rid, "status": status, "headers": headers, "body": base64.b64encode(data).decode()}


# ---------------------------------------------------------------------------
# Remote password: each time a hub user opens the bot (one hub "rsid"), they
# enter it once. Unlocks live in memory, so a bot restart asks again.
# ---------------------------------------------------------------------------

_unlocked = {}   # unlock key -> last use (epoch)
_fails = {}      # hub user -> [failures, locked_until]


def unlock_key(user: str, sid: str) -> str:
    return f"{user}|{sid}"


def is_unlocked(key: str) -> bool:
    now = time.time()
    with _lock:
        t = _unlocked.get(key)
        if t is None or now - t > UNLOCK_IDLE:
            _unlocked.pop(key, None)
            return False
        _unlocked[key] = now
        return True


def locked_out(user: str) -> int:
    """Seconds this hub user must wait before trying again (0 = may try)."""
    with _lock:
        f = _fails.get(user)
    return max(0, int(f[1] - time.time())) if f and f[1] else 0


def try_unlock(user: str, key: str, given: str, expected: str) -> bool:
    import hmac
    if locked_out(user):
        return False
    ok = hmac.compare_digest(given.encode(), expected.encode())
    with _lock:
        if ok:
            _fails.pop(user, None)
            _unlocked[key] = time.time()
        else:
            f = _fails.setdefault(user, [0, 0])
            f[0] += 1
            if f[0] >= MAX_FAILS:
                f[0], f[1] = 0, time.time() + LOCKOUT
    return ok


def lock_all():
    """Remote password changed: everyone has to enter it again."""
    with _lock:
        _unlocked.clear()


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
        global _unpair_requested
        with _lock:
            known = _state["status"]
        allow_plugins = bool(cfg.load().get("remote", {}).get("allow_plugins", False))
        payload = {"version": _version(), "session": _SESSION, "known_status": known,
                   "plugins_allowed": allow_plugins, "plugins_state": plugin_sync.state()}
        code = _active_code()
        if code:
            payload["pair_code"] = code
        with _lock:
            unpair = _unpair_requested
        if unpair:
            payload["unpair"] = True
        try:
            d = _post(url, key, "/api/remote/poll", payload, POLL_TIMEOUT)
        except urllib.error.HTTPError as e:
            _set("error", hub_errors.describe(e, url))
            time.sleep(30)
            continue
        except Exception as e:
            _set("error", hub_errors.describe(e, url))
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        backoff = 5
        if unpair:
            with _lock:
                _unpair_requested = False
        if d.get("pair_code_used"):
            cancel_pairing()
        st = d.get("status", "")
        _set(st or "error", "", owner=d.get("owner", ""), shared=int(d.get("shared") or 0))
        try:
            # Re-read: the setting may have changed while the poll was held.
            allowed_now = bool(cfg.load().get("remote", {}).get("allow_plugins", False))
            if not allowed_now:
                plugin_sync.apply([])     # switched off here: remove hub-installed plugins
            elif allow_plugins and isinstance(d.get("plugins"), list):
                plugin_sync.apply(d["plugins"], url, key)
        except Exception as e:
            log.warning("Plugin sync failed: %s", e)
        if st != "paired":
            _wake.wait(PAIRING_WAIT if _active_code() else UNPAIRED_WAIT + n * 3)
            _wake.clear()
            continue
        for frame in d.get("requests") or []:
            resp = handle(frame)
            try:
                _post(url, key, "/api/remote/respond", resp, 30)
            except Exception as e:
                log.warning("Remote respond failed: %s", e)


def _feed_worker():
    """Send new action history rows to the hub while paired and sharing is on.

    The hub keeps the latest 2,000 per bot for the Activity feed on its Remote
    page. Only live rows are sent (not ones imported from old log files)."""
    cursor = None          # last action id the hub has from this bot
    last_target = None
    shared = False         # sent anything this run (so a switch-off clears the hub's copy)
    while True:
        time.sleep(FEED_EVERY)
        try:
            target, _ = settings()
            with _lock:
                paired = _state["status"] == "paired"
            share = bool(cfg.load().get("remote", {}).get("share_actions", True))
            if target != last_target:
                cursor, last_target = None, target
            if not target or not paired:
                cursor = None
                continue
            url, key = target
            if not share:
                if shared:
                    _post(url, key, "/api/remote/actions", {"clear": True}, 15)
                    shared = False
                cursor = None
                continue
            if cursor is None:
                local = action_log.max_id()
                d = _post(url, key, "/api/remote/actions", {"hello": True, "max_id": local}, 15)
                # The hub forgets its copy if this bot's history was reset
                # (its last id is above ours) and answers 0.
                cursor = max(int(d.get("last_id") or 0), local - FEED_BACKFILL, 0)
                shared = True
            rows = action_log.feed_rows(cursor, FEED_BATCH)
            if not rows:
                continue
            _post(url, key, "/api/remote/actions", {"actions": rows}, 15)
            cursor = rows[-1]["id"]
        except urllib.error.HTTPError as e:
            cursor = None
            if e.code == 404:
                time.sleep(300)      # the hub doesn't have the feed yet
        except Exception as e:
            log.debug("Action feed upload failed: %s", e)
            cursor = None


def _state_key(snap: dict) -> str:
    """Comparison key for a status snapshot. Countdowns shrink every second,
    so they are compared as the (rounded) time they end: a bot whose timers
    just tick down isn't resent every few seconds, but a reset timer is."""
    now = time.time()

    def ends(v):
        return None if v is None else int((now + v) // 10)

    card = dict(snap.get("card") or {})
    details = dict(snap.get("details") or {})
    for d in (card, details):
        for k in [k for k in d if k.endswith("_left")]:
            d[k] = ends(d[k])
    details["timers"] = {n: ends(v) for n, v in (details.get("timers") or {}).items()}
    details.pop("server_time", None)
    return json.dumps({"card": card, "details": details}, sort_keys=True, default=str)


def _state_worker():
    """Send the game status shown on the hub's Remote page while paired:
    every STATE_EVERY seconds when it changed, else every STATE_HEARTBEAT."""
    last, last_sent = None, 0.0
    while True:
        time.sleep(STATE_EVERY)
        try:
            target, _ = settings()
            with _lock:
                paired = _state["status"] == "paired"
            if not target or not paired:
                last = None
                continue
            snap = hub_state.snapshot()
            key = _state_key(snap)
            if key == last and time.time() - last_sent < STATE_HEARTBEAT:
                continue
            url, key_ = target
            _post(url, key_, "/api/remote/state", {"state": snap}, 15)
            last, last_sent = key, time.time()
        except urllib.error.HTTPError as e:
            last = None
            if e.code == 404:
                time.sleep(300)      # the hub doesn't take status yet
        except Exception as e:
            log.debug("Status upload failed: %s", e)
            last = None


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
    threading.Thread(target=_feed_worker, name="remote-feed", daemon=True).start()
    threading.Thread(target=_state_worker, name="remote-state", daemon=True).start()
    import comms_forward
    comms_forward.start()


def nudge():
    """Settings changed: re-check now instead of after the idle wait."""
    _wake.set()
