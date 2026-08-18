"""
Communications (in-game messaging) tasks.

CommsCheckTask    — triggered when comms_span_id class indicates unread messages.
CommsSendTask     — sends a new conversation or reply, triggered from UI queue.
CommsArchiveTask  — explicit, triggered from UI via a queue.
"""

import json
import queue
import re
from pathlib import Path

from tasks.base import Task, Action
from state import GameState

import urls as _urls


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _comms_dir() -> Path:
    from paths import data_dir
    return Path(data_dir()) / "communications"


def _comms_path(char_name: str) -> Path:
    return _comms_dir() / f"messages_{char_name}.json"


def _load_comms(char_name: str) -> dict:
    p = _comms_path(char_name)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_comms(char_name: str, data: dict):
    p = _comms_path(char_name)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Inbox parsing  (comms.asp?display=inbox)
# ---------------------------------------------------------------------------

def parse_inbox_rows(soup) -> list[dict]:
    """Return list of conversation metadata dicts from inbox page."""
    conversations = []
    for row in soup.find_all("div", class_="mailRow"):
        conv = {}

        # conversation id from checkbox or viewconv link
        cb = row.find("input", attrs={"name": "delsel"})
        if cb:
            conv["conv_id"] = cb.get("value", "")
        else:
            link = row.find("a", class_="mailRowContent")
            if link:
                m = re.search(r"id=(\d+)", link.get("href", ""))
                if m:
                    conv["conv_id"] = m.group(1)
        if not conv.get("conv_id"):
            continue

        # started by
        starter_h1 = row.find("h1")
        if starter_h1:
            starter_a = starter_h1.find("a")
            conv["started_by"] = starter_a.get_text(strip=True) if starter_a else ""

        # other player (profile link in the table, not the "Started by" link)
        profile_links = row.find_all("a", href=re.compile(r"/userprofile\.asp\?u="))
        for a in profile_links:
            name = a.get_text(strip=True)
            if name and name != conv.get("started_by", ""):
                conv["other_player"] = name
                break
        if "other_player" not in conv:
            for a in profile_links:
                name = a.get_text(strip=True)
                if name:
                    conv["other_player"] = name
                    break

        # subject
        subj_el = row.find("span", class_="mailRowSubject")
        conv["subject"] = subj_el.get_text(strip=True) if subj_el else ""

        # excerpt
        exc_el = row.find("span", class_="mailRowExcerpt")
        conv["excerpt"] = exc_el.get_text(strip=True) if exc_el else ""

        # timestamp
        ts_el = row.find("abbr", class_="timestamp")
        conv["last_message_time"] = ts_el.get("title", "").replace("Last message: ", "") if ts_el else ""

        # message count
        mc_el = row.find("span", class_="mailRowMessages")
        try:
            conv["message_count"] = int(mc_el.get_text(strip=True)) if mc_el else 0
        except ValueError:
            conv["message_count"] = 0

        conversations.append(conv)
    return conversations


# ---------------------------------------------------------------------------
# Thread parsing  (comms.asp?display=viewconv&id=N)
# ---------------------------------------------------------------------------

def parse_thread(soup) -> dict:
    """Parse a conversation thread page. Returns {subject, conv_id, messages: [...]}."""
    result = {"subject": "", "conv_id": "", "messages": []}

    # subject from h2 > i
    h2 = soup.find("h2")
    if h2:
        i_tag = h2.find("i")
        result["subject"] = i_tag.get_text(strip=True) if i_tag else h2.get_text(strip=True).strip('"')

    # conv_id from hidden input
    hidden = soup.find("input", attrs={"name": "sendconvid"})
    if hidden:
        result["conv_id"] = hidden.get("value", "")

    # messages within conversation_holder
    holder = soup.find("div", id="conversation_holder")
    if not holder:
        return result

    for msg_row in holder.find_all("div", class_="mailRow"):
        msg = {}

        # msg_id from checkbox, forward link, or delete link
        cb = msg_row.find("input", attrs={"name": "delsel"})
        if cb:
            msg["msg_id"] = cb.get("value", "")
        else:
            for a in msg_row.find_all("a", href=True):
                m = re.search(r"id=(\d+)", a.get("href", ""))
                if m:
                    msg["msg_id"] = m.group(1)
                    break

        # sender
        sender_link = msg_row.find("a", href=re.compile(r"/userprofile\.asp\?u="))
        if sender_link:
            um = re.search(r"u=([^&]+)", sender_link["href"])
            msg["from"] = um.group(1) if um else sender_link.get_text(strip=True)
        else:
            msg["from"] = ""

        # timestamp
        ts_el = msg_row.find("abbr", class_="timestamp")
        msg["time"] = ts_el.get("title", "").replace("Last message: ", "") if ts_el else ""

        # body — the div with color: #fff inside the message
        body_div = msg_row.find("div", style=re.compile(r"color:\s*#fff"))
        if body_div:
            msg["body"] = body_div.get_text("\n", strip=True)
        else:
            msg["body"] = ""

        if msg.get("from"):
            result["messages"].append(msg)

    return result


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

def inbox_next_page_url(soup) -> "str | None":
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if re.search(r"comms\.asp\?.*p=\d+", href) and a.get_text(strip=True) == "Next":
            if href.startswith("http"):
                return href
            return _urls.BASE_URL + "/communications/" + href
    return None


def is_inbox_last_page(soup) -> bool:
    for span in soup.find_all("span", class_="selected"):
        if span.get_text(strip=True) == "Next":
            return True
    return True  # default to last page if no paging found


# ---------------------------------------------------------------------------
# Queues
# ---------------------------------------------------------------------------

_comms_send_queue: "queue.Queue | None" = None
_comms_archive_queue: "queue.Queue | None" = None


def set_comms_send_queue(q: "queue.Queue"):
    global _comms_send_queue
    _comms_send_queue = q


def set_comms_archive_queue(q: "queue.Queue"):
    global _comms_archive_queue
    _comms_archive_queue = q


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class CommsCheckTask(Task):
    priority = 34
    label = "Comms Check"

    def can_run(self, state: GameState) -> bool:
        import config
        if not config.load().get("communications", {}).get("enabled", False):
            return False
        return state.logged_in and state.has_new_comms

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if not state.has_new_comms:
            reasons.append("No new messages")
        return reasons

    def run(self, state: GameState, executor):
        executor.execute(Action("check_comms"), state)


class CommsSendTask(Task):
    priority = 37
    label = "Comms Send"

    def __init__(self, send_queue: queue.Queue):
        self._queue = send_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not self._queue.empty()

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        try:
            params = self._queue.get_nowait()
        except Exception:
            return
        action_kind = params.pop("_action", "send_comms")
        executor.execute(Action(action_kind, **params), state)


class CommsArchiveTask(Task):
    priority = 5
    label = "Archive Comms"

    def __init__(self, archive_queue: queue.Queue):
        self._queue = archive_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not self._queue.empty()

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        try:
            params = self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("archive_comms", **params), state)
