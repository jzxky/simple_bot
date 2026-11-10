"""
plugin_sync.py — Keep hub-installed plugins in step with Player Hub.

When Settings → Remote control → "Allow plugins from the hub" is on (only
changeable on this computer), each remote-control poll tells the hub so, and
the hub answers with the plugins this bot's owner picked for it on the hub's
Remote page: [{"name", "version", "sha256"}]. Missing or changed files are
downloaded with the bot's API key, checked against the sha256, and written to
the plugins folder; hub-installed files the hub no longer lists are deleted.

Hub-installed files are recorded in plugins/.hub.json. Files you put in the
plugins folder yourself are never touched unless the hub installs a plugin of
the same name. Plugins load when the bot starts (ui.app.load_plugins), so a
change takes effect after a restart.
"""

import hashlib
import json
import logging
import os
import re
import threading
import urllib.request

import paths

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9_]{1,40}$")
MAX_SIZE = 512 * 1024

_lock = threading.Lock()
_sync_lock = threading.Lock()
_loaded = {}      # plugin name -> sha256 of the file this run loaded
_errors = {}      # plugin name -> last problem
_removed = set()  # hub plugins deleted while still loaded (gone after a restart)


def folder() -> str:
    return os.path.join(paths.data_dir(), "plugins")


def _registry_path() -> str:
    return os.path.join(folder(), ".hub.json")


def _registry() -> dict:
    try:
        with open(_registry_path(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_registry(reg: dict):
    os.makedirs(folder(), exist_ok=True)
    tmp = _registry_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, indent=1, sort_keys=True)
    os.replace(tmp, _registry_path())


def _file_sha(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Called by ui.app.load_plugins at startup
# ---------------------------------------------------------------------------

def note_loaded(name: str, path: str):
    with _lock:
        _loaded[name] = _file_sha(path)
        _errors.pop(name, None)


def note_error(name: str, msg: str):
    with _lock:
        _errors[name] = str(msg)[:300]


# ---------------------------------------------------------------------------
# State reported to the hub and shown in the control panel
# ---------------------------------------------------------------------------

def state() -> dict:
    """{"installed": {name: version}, "loaded": {name: version}, "errors": {name: msg}}
    for hub-installed plugins."""
    reg = _registry()
    with _lock:
        loaded, errors = dict(_loaded), dict(_errors)
    installed = {n: v.get("version") for n, v in reg.items()
                 if os.path.isfile(os.path.join(folder(), n + ".py"))}
    running = {n: v.get("version") for n, v in reg.items() if loaded.get(n) == v.get("sha256")}
    return {"installed": installed, "loaded": running,
            "errors": {n: m for n, m in errors.items() if n in reg}}


def summary() -> dict:
    """For the control panel: hub plugins and whether a restart is needed."""
    reg = _registry()
    with _lock:
        loaded, errors, removed = dict(_loaded), dict(_errors), set(_removed)
    items = []
    for n, v in sorted(reg.items()):
        if n in errors:
            st = "error"
        elif loaded.get(n) == v.get("sha256"):
            st = "running"
        else:
            st = "restart"
        items.append({"name": n, "version": v.get("version"), "state": st, "error": errors.get(n, "")})
    return {"plugins": items, "removed": sorted(removed),
            "restart_needed": any(i["state"] == "restart" for i in items) or bool(removed)}


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------

def _download(url: str, key: str, name: str) -> bytes:
    req = urllib.request.Request(f"{url}/api/plugins/download/{name}",
                                 headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read(MAX_SIZE + 1)
    if len(data) > MAX_SIZE:
        raise ValueError("file too big")
    return data


def apply(manifest, url: str = "", key: str = "") -> bool:
    """Make the hub-installed plugins match `manifest`. Returns False if
    another sync was already running (it will catch up on the next poll)."""
    if not _sync_lock.acquire(blocking=False):
        return False
    try:
        wanted = {}
        for m in manifest or []:
            if isinstance(m, dict) and NAME_RE.match(str(m.get("name", ""))) and m.get("sha256"):
                wanted[m["name"]] = m
        reg = _registry()
        changed = False

        for name, m in wanted.items():
            path = os.path.join(folder(), name + ".py")
            if reg.get(name, {}).get("sha256") == m["sha256"] and _file_sha(path) == m["sha256"]:
                continue
            if not url:
                continue
            try:
                data = _download(url, key, name)
                if hashlib.sha256(data).hexdigest() != m["sha256"]:
                    raise ValueError("the download didn't match the hub's checksum")
                os.makedirs(folder(), exist_ok=True)
                tmp = path + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, path)
            except Exception as e:
                note_error(name, f"Download failed: {e}")
                log.warning("Plugin %s download failed: %s", name, e)
                continue
            reg[name] = {"version": m.get("version"), "sha256": m["sha256"]}
            changed = True
            with _lock:
                _errors.pop(name, None)
                _removed.discard(name)
            log.info("Plugin %s v%s downloaded from the hub; restart the bot to load it.", name, m.get("version"))

        for name in [n for n in reg if n not in wanted]:
            try:
                os.remove(os.path.join(folder(), name + ".py"))
            except FileNotFoundError:
                pass
            except OSError as e:
                note_error(name, f"Couldn't delete it: {e}")
                continue
            del reg[name]
            changed = True
            with _lock:
                _errors.pop(name, None)
                if name in _loaded:
                    _removed.add(name)
            log.info("Plugin %s removed by the hub; restart the bot to unload it.", name)

        if changed:
            _save_registry(reg)
        return True
    finally:
        _sync_lock.release()
