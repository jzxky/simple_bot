"""
Top job forum post: the announcement made in the thread set in the top job
sniper settings (promo.top_job_thread_id) after a top job promotion.

A promotion taken by any route (the sniper in the side browser, or the
promotion page handler on the main tab) records a *pending post* in
promo_post_pending.json. The record outlives errors and restarts:

  - PromoForumPostTask (tasks/promo_forum_post.py) keeps trying until a post
    has been submitted, urgently travelling home first when the character is
    away; an error part-way leaves the record for the next try;
  - every attempt first checks the reply page's "last 5 posts" list, so a
    retry never posts twice;
  - after submitting, the list is checked again and a notification says
    whether the post was found.

The post is "<name> - <top job> - <server time of the promotion>".

All page work goes through post_and_verify(page, state), which works on any
patchright page (main tab or side browser) and holds a lock so the two
browsers never post at the same time.
"""

import json
import os
import re
import threading
from datetime import datetime

import config as cfg
import paths
import urls

_LOCK = threading.Lock()
_PATH = os.path.join(paths.data_dir(), "promo_post_pending.json")
_NAV_TIMEOUT = 20000


# ---------------------------------------------------------------------------
# Pending record
# ---------------------------------------------------------------------------

def thread_id() -> str:
    return str(cfg.load().get("promo", {}).get("top_job_thread_id", "") or "").strip()


def load() -> "dict | None":
    try:
        with open(_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get("top_job") else None
    except Exception:
        return None


def _save(data: dict):
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def clear():
    try:
        os.remove(_PATH)
    except FileNotFoundError:
        pass


def pending_for(state) -> "dict | None":
    """The pending post for the logged-in character, if any."""
    p = load()
    if not p:
        return None
    if state.own_name and p.get("character") and p["character"].lower() != state.own_name.lower():
        return None
    return p


def mark_pending(state, top_job: str):
    """Record that `top_job` was just taken and needs its forum post. Does
    nothing when no thread is set. Keeps an existing record for the same job
    (its promotion time and attempt history stay)."""
    if not thread_id():
        state.add_log(f"Top job post: promoted to {top_job} — no forum thread set, nothing to post.")
        return
    existing = pending_for(state)
    if existing and existing.get("top_job") == top_job:
        return
    from state import SERVER_TIME_FMT
    ts = state.server_time.strftime(SERVER_TIME_FMT) if state.server_time else "?"
    _save({
        "character": state.own_name or "",
        "top_job": top_job,
        "promoted_at": ts,
        "submits": 0,
        "attempts": 0,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    state.add_log(f"Top job post: {top_job} taken — forum post pending.")


def message(p: dict) -> str:
    return f"{p.get('character', '')} - {p['top_job']} - {p.get('promoted_at', '?')}"


# ---------------------------------------------------------------------------
# Page work
# ---------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _goto(pg, url: str):
    pg.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT)


def _reply_url(tid: str) -> str:
    return urls.BASE_URL + f"/forum/postreply.asp?t={tid}"


# The reply page lists the thread's last 5 posts under #post_list: one
# tr.alias per post, author link in the first cell, text in #bodytext.
_RECENT_POSTS_JS = """() => {
  const list = document.querySelector('#post_list');
  if (!list) return null;
  return Array.from(list.querySelectorAll('tr.alias')).map(tr => {
    const a = tr.querySelector('td a');
    const body = tr.querySelector('#bodytext, .bodytext');
    return {author: a ? a.textContent : '', body: body ? body.textContent : ''};
  });
}"""


def recent_posts(pg, tid: str) -> "list | None":
    """The last 5 posts listed on the thread's reply page, or None if the list
    isn't on the page."""
    _goto(pg, _reply_url(tid))
    try:
        return pg.evaluate(_RECENT_POSTS_JS)
    except Exception:
        return None


def is_posted(pg, p: dict, tid: str) -> "bool | None":
    """True if the post is in the reply page's last-5 list (by this character,
    with this text), False if it isn't, None if the list couldn't be read."""
    posts = recent_posts(pg, tid)
    if posts is None:
        return None
    msg = _norm(message(p))
    who = _norm(p.get("character", ""))
    return any(msg in _norm(x.get("body")) and (not who or _norm(x.get("author")) == who)
               for x in posts)


def post_and_verify(pg, state) -> bool:
    """Make the pending post unless it's already in the thread, then check the
    reply page's last-5 list for it and notify whether it was found. Returns
    True once handled (record cleared). Raises on page errors, leaving the
    record for a retry. Must be called with the character in its home city."""
    with _LOCK:
        p = pending_for(state)
        if not p:
            return True
        tid = thread_id()
        if not tid:
            state.add_log("Top job post: no forum thread set — dropping the pending post.")
            clear()
            return True
        p["attempts"] = int(p.get("attempts", 0)) + 1
        _save(p)
        msg = message(p)

        # A retry after an error: the earlier attempt may have posted already.
        before = is_posted(pg, p, tid)
        if before:
            state.add_log(f"Top job post: found in the thread — \"{msg}\" (already posted).")
            _note(state, f"Top job post found in the thread: {msg}")
            clear()
            return True
        if before is None and int(p.get("submits", 0)) > 0:
            state.add_log("Top job post: a post was submitted earlier but the thread's recent posts "
                          "can't be read — not posting again.")
            _note(state, f"Top job post for {p['top_job']} NOT confirmed (couldn't read the thread) — check it.")
            clear()
            return True

        # recent_posts() left the page on the reply form.
        pg.fill("textarea#body", msg)
        p["submits"] = int(p.get("submits", 0)) + 1
        _save(p)
        pg.click("input[name='Submit']")
        pg.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT)

        after = is_posted(pg, p, tid)
        clear()
        if after:
            state.add_log(f"Top job post: posted and found in the thread — \"{msg}\".")
            _note(state, f"Top job post found in the thread: {msg}")
        elif after is None:
            state.add_log(f"Top job post: submitted \"{msg}\" — couldn't read the thread's recent posts to check.")
            _note(state, f"Top job post NOT confirmed (couldn't read the thread): {msg}")
        else:
            state.add_log(f"Top job post: submitted \"{msg}\" but it's not in the thread's last 5 posts.")
            _note(state, f"Top job post NOT found in the thread: {msg}")
        return True


def _note(state, msg: str):
    if cfg.load().get("notifications", {}).get("promo_forum_post", True):
        state.push_notification("promo_forum_post", msg)
