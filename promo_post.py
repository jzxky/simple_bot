"""
Top job forum post: the announcement made in the thread set in the top job
sniper settings (promo.top_job_thread_id) after a top job promotion.

A promotion taken by any route (the sniper in the side browser, or the
promotion page handler on the main tab) records a *pending post* in
promo_post_pending.json. The record outlives errors and restarts, and is only
cleared once the post has been seen in the thread, so:

  - PromoForumPostTask (tasks/promo_forum_post.py) keeps trying until it's
    done, urgently travelling home first when the character is away;
  - every attempt first checks the thread for the post, so a retry after an
    error never posts twice;
  - after submitting, the post is checked for in the thread before the
    record is cleared.

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


def _page_has(pg, msg: str) -> bool:
    try:
        return _norm(msg) in _norm(pg.inner_text("body"))
    except Exception:
        return False


def _goto(pg, url: str):
    pg.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT)


def _thread_link(pg, tid: str) -> "str | None":
    """A link to the thread itself (not the reply form) on the current page."""
    pat = re.compile(rf"[?&]t(?:opic)?(?:id)?={re.escape(tid)}(?:&|$)", re.I)
    best = None
    for a in pg.query_selector_all("a[href]"):
        href = a.get_attribute("href") or ""
        if not pat.search(href) or "postreply" in href.lower() or "javascript:" in href.lower():
            continue
        best = best or href
    if not best:
        return None
    if best.startswith("http"):
        return best
    if best.startswith("/"):
        return urls.BASE_URL + best
    return urls.BASE_URL + "/forum/" + best


def _last_page_links(pg, tid: str) -> list:
    """Links to this thread's two highest-numbered pages on the current page,
    highest first (the post is on the last page, or the one before it if the
    thread has moved on since)."""
    pat = re.compile(rf"[?&]t(?:opic)?(?:id)?={re.escape(tid)}(?:&|$)", re.I)
    pages = {}
    for a in pg.query_selector_all("a[href]"):
        href = a.get_attribute("href") or ""
        if not pat.search(href) or "postreply" in href.lower():
            continue
        m = re.search(r"[?&](?:page|p|pg|whichpage)=(\d+)", href, re.I)
        if m and int(m.group(1)) > 1:
            pages.setdefault(int(m.group(1)), href)
    out = []
    for n in sorted(pages, reverse=True)[:2]:
        href = pages[n]
        if href.startswith("http"):
            out.append(href)
        elif href.startswith("/"):
            out.append(urls.BASE_URL + href)
        else:
            out.append(urls.BASE_URL + "/forum/" + href)
    return out


def check_posted(pg, p: dict, tid: str) -> "bool | None":
    """True if the post is in the thread, False if the thread was read and it
    isn't, None if the thread couldn't be found to check."""
    msg = message(p)
    _goto(pg, urls.BASE_URL + f"/forum/postreply.asp?t={tid}")
    if _page_has(pg, msg):          # reply form's topic review, if it has one
        return True
    link = _thread_link(pg, tid)
    if not link:
        return None
    _goto(pg, link)
    if _page_has(pg, msg):
        return True
    for url in _last_page_links(pg, tid):
        _goto(pg, url)
        if _page_has(pg, msg):
            return True
    return False


def post_and_verify(pg, state) -> bool:
    """Make the pending post (if it isn't in the thread already) and confirm
    it's there. Returns True once the post is confirmed and the record cleared.
    Must be called with the character in its home city."""
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

        before = check_posted(pg, p, tid)
        if before:
            state.add_log(f"Top job post: already in the thread — \"{msg}\".")
            clear()
            return True
        if before is None and int(p.get("submits", 0)) > 0:
            # Can't read the thread and a submit already went through once:
            # posting again could double post, so stop and let the user check.
            state.add_log("Top job post: a post was submitted but the thread can't be read to "
                          "confirm it — not posting again. Check the thread.")
            _note(state, f"Top job post for {p['top_job']} couldn't be confirmed — check the thread.")
            clear()
            return True

        _goto(pg, urls.BASE_URL + f"/forum/postreply.asp?t={tid}")
        pg.fill("textarea#body", msg)
        p["submits"] = int(p.get("submits", 0)) + 1
        _save(p)
        pg.click("input[name='Submit']")
        pg.wait_for_load_state("domcontentloaded", timeout=_NAV_TIMEOUT)
        landed = _page_has(pg, msg)

        after = True if landed else check_posted(pg, p, tid)
        if after:
            state.add_log(f"Top job post: posted and confirmed in the thread — \"{msg}\".")
            _note(state, f"Top job forum post made: {msg}")
            clear()
            return True
        if after is None:
            state.add_log(f"Top job post: submitted \"{msg}\" — the thread couldn't be read to confirm it. "
                          "Check the thread.")
            _note(state, f"Top job post submitted but not confirmed — check the thread.")
            clear()
            return True
        state.add_log(f"Top job post: submitted but not found in the thread — will retry.")
        return False


def _note(state, msg: str):
    if cfg.load().get("notifications", {}).get("promo_forum_post", True):
        state.push_notification("promo_forum_post", msg)
