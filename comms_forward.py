"""
comms_forward.py — Send new in-game messages to Player Hub, which DMs them to
this bot's owner on Discord (if they linked Discord on the hub's Remote page).

Only runs while Settings → Remote control → "Forward in-game messages to the
hub" is on (remote.forward_comms, changeable only on this computer) and the bot
is paired. The inbox check (executor.handle_check_comms) queues messages from
other players; a background thread posts them to /api/comms/messages. The
queue is kept in comms_outbox.json so messages survive a restart or a hub
outage. Turning the setting off empties it.
"""

import hashlib
import json
import logging
import os
import threading
import time
import urllib.error

import config as cfg
import paths

log = logging.getLogger(__name__)

OUTBOX_PATH = os.path.join(paths.data_dir(), "comms_outbox.json")
OUTBOX_MAX = 300          # oldest dropped beyond this
SEND_EVERY = 10           # seconds
BATCH = 50

_lock = threading.Lock()
_started = False


def enabled() -> bool:
    return bool(cfg.load().get("remote", {}).get("forward_comms", False))


def _read() -> list:
    try:
        with open(OUTBOX_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write(rows: list):
    if not rows:
        try:
            os.remove(OUTBOX_PATH)
        except FileNotFoundError:
            pass
        return
    tmp = OUTBOX_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False)
    os.replace(tmp, OUTBOX_PATH)


def msg_key(conv_id: str, msg: dict) -> str:
    """The game's message id, or a stable stand-in when the page had none."""
    mid = str(msg.get("msg_id") or "").strip()
    if mid:
        return mid
    raw = "|".join([str(conv_id), msg.get("from", ""), msg.get("time", ""), msg.get("body", "")])
    return "h" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def new_incoming(conv_id: str, old_msgs: list, new_msgs: list, own_name: str) -> list:
    """Messages in new_msgs that weren't in old_msgs and weren't sent by us."""
    seen = {msg_key(conv_id, m) for m in old_msgs or []}
    me = (own_name or "").lower()
    return [m for m in new_msgs or []
            if msg_key(conv_id, m) not in seen and (m.get("from") or "").lower() != me]


def queue(character: str, conv: dict, msgs: list):
    """Queue messages for the hub. No-op unless forwarding is on."""
    if not msgs or not enabled():
        return
    cid = str(conv.get("conv_id", ""))
    rows = [{
        "msg_id": msg_key(cid, m),
        "conv_id": cid,
        "character": character or "",
        "sender": m.get("from", "") or conv.get("other_player", ""),
        "subject": conv.get("subject", ""),
        "body": m.get("body", ""),
        "time": m.get("time", ""),
    } for m in reversed(msgs)]          # the game lists newest first; send oldest first
    with _lock:
        out = _read() + rows
        _write(out[-OUTBOX_MAX:])


def pending() -> int:
    with _lock:
        return len(_read())


def send_once(post, url: str, key: str) -> int:
    """Post one batch; returns how many the hub took. post(url, key, path, payload, timeout)."""
    with _lock:
        rows = _read()[:BATCH]
    if not rows:
        return 0
    d = post(url, key, "/api/comms/messages", {"messages": rows}, 15)
    if not d.get("ok"):
        return 0        # the hub says this bot isn't paired: keep them for now
    sent = {r["msg_id"] for r in rows}
    with _lock:
        _write([r for r in _read() if r.get("msg_id") not in sent])
    return len(rows)


def _worker():
    import remote_control
    while True:
        time.sleep(SEND_EVERY)
        try:
            if not enabled():
                with _lock:
                    if os.path.exists(OUTBOX_PATH):
                        _write([])
                continue
            target, _ = remote_control.settings()
            if not target or remote_control.status().get("status") != "paired":
                continue
            while send_once(remote_control._post, *target) == BATCH:
                pass
        except urllib.error.HTTPError as e:
            if e.code == 404:
                time.sleep(300)       # the hub doesn't support this yet
        except Exception as e:
            log.debug("Forwarding in-game messages failed: %s", e)


def start():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_worker, name="comms-forward", daemon=True).start()
