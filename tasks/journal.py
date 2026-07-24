"""
Journal checking and archiving tasks.

JournalCheckTask  — low-priority, triggered when journals_span_id class changes.
ArchiveJournalsTask — explicit, triggered from UI via a queue.
"""

import json
import queue
import re
from datetime import datetime
from pathlib import Path

from tasks.base import Task, Action
from state import GameState

import urls as _urls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _journals_dir() -> Path:
    from paths import data_dir
    return Path(data_dir()) / "journals"


def _journals_path(char_name: str) -> Path:
    return _journals_dir() / f"journals_{char_name}.json"


def _migrate_journal_files():
    import shutil as _shutil
    from paths import data_dir
    d = Path(data_dir())
    jdir = _journals_dir()
    jdir.mkdir(exist_ok=True)
    for f in d.glob("journals_*.json"):
        dest = jdir / f.name
        if not dest.exists():
            _shutil.move(str(f), str(dest))

_migrate_journal_files()


def _load_journals(char_name: str) -> dict:
    p = _journals_path(char_name)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_journals(char_name: str, data: dict):
    p = _journals_path(char_name)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_label(label) -> tuple[str, str, str, str]:
    """Return (entry_id, title, time_str, text) from a journal label element."""
    entry_id = label.get("for", "").strip()
    title_el = label.find("strong", class_="title")
    time_el = label.find("span", class_="time")
    title = title_el.get_text(strip=True) if title_el else ""
    time_str = time_el.get_text(strip=True) if time_el else ""
    # Only remove the header elements (title strong + time span + br tags),
    # leaving inline <strong>PlayerName</strong> in the body text.
    for el in [title_el, time_el] + label.find_all("br"):
        if el:
            el.decompose()
    text = re.sub(r"\s+", " ", label.get_text(" ", strip=True))
    return entry_id, title, time_str, text


def _extract_action_urls(journal_row):
    """Extract accept/decline URLs from sibling rows after a journal_row."""
    accept_url = ""
    decline_url = ""
    sibling = journal_row.find_next_sibling("tr")
    if not sibling:
        return accept_url, decline_url
    for a in sibling.find_all("a", href=True):
        href = a["href"]
        if "actionevent.asp" not in href:
            continue
        if "action=accept" in href:
            accept_url = href if href.startswith("http") else href
        elif "action=decline" in href:
            decline_url = href if href.startswith("http") else href
    return accept_url, decline_url


# Journal markup differs in jail: rows/cells/new-marker use jail_-prefixed
# classes/ids. Match both so journals log while jailed as well as free.
_ROW_CLASSES     = {"journal_row", "jail_journal_row"}
_EVENT_CLASSES   = {"journal_event", "jail_journal_event"}
_NEW_MARKER_IDS  = ("comms_msg_top_super", "jail_comms_msg_top_super")


def _journal_rows(soup):
    """Yield every journal row tag (normal or jail variant)."""
    for row in soup.find_all("tr"):
        if set(row.get("class", []) or []) & _ROW_CLASSES:
            yield row


def _event_td(row):
    """The journal_event / jail_journal_event cell of a row, or None."""
    for td in row.find_all("td"):
        if set(td.get("class", []) or []) & _EVENT_CLASSES:
            return td
    return None


def _parse_journal_rows(soup) -> list[dict]:
    """Return list of dicts with id/title/time/text for every journal row on the page."""
    entries = []
    for row in _journal_rows(soup):
        td = _event_td(row)
        if not td:
            continue
        label = td.find("label")
        if not label:
            continue
        entry_id, title, time_str, text = _parse_label(label)
        if entry_id:
            entries.append({"id": entry_id, "title": title, "time": time_str, "text": text})
    return entries


def _has_new_marker_before(soup, row_tag) -> bool:
    """Return True if the journal row immediately follows a NEW marker tr."""
    prev = row_tag.find_previous_sibling("tr")
    if prev:
        for marker_id in _NEW_MARKER_IDS:
            if prev.find("td", id=marker_id):
                return True
    return False


def _new_entries_on_page(soup) -> list[dict]:
    """Return only the NEW-flagged entries on this page."""
    new = []
    for row in _journal_rows(soup):
        if _has_new_marker_before(soup, row):
            td = _event_td(row)
            if not td:
                continue
            label = td.find("label")
            if not label:
                continue
            entry_id, title, time_str, text = _parse_label(label)
            if entry_id:
                new.append({"id": entry_id, "title": title, "time": time_str, "text": text})
    return new


def _is_last_page(soup) -> bool:
    """True when the Next link is disabled (span.selected containing 'Next')."""
    for span in soup.find_all("span", class_="selected"):
        if span.get_text(strip=True) == "Next":
            return True
    return False


def _next_page_url(soup) -> "str | None":
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if re.search(r"journal\.asp\?p=\d+", href) and a.get_text(strip=True) == "Next":
            if href.startswith("http"):
                return href
            return _urls.BASE_URL + "/journal/" + href
    return None


_drug_trade_queue: "queue.Queue | None" = None
_illness_queue: "queue.Queue | None" = None
_repair_complete_queue: "queue.Queue | None" = None

_FLU_TEXT = "you have a slightly nauseous feeling in your stomach"


def set_drug_trade_queue(q: "queue.Queue"):
    global _drug_trade_queue
    _drug_trade_queue = q


def set_illness_queue(q: "queue.Queue"):
    global _illness_queue
    _illness_queue = q


def set_repair_complete_queue(q: "queue.Queue"):
    global _repair_complete_queue
    _repair_complete_queue = q


def dispatch_journal_action(entry: dict, state: GameState):
    import config as cfg
    if entry.get("title") == "Drug Trade Offer":
        if cfg.load().get("autobuy", {}).get("enabled", False):
            if _drug_trade_queue is not None:
                _drug_trade_queue.put(True)
    if entry.get("title") == "Illness":
        if _FLU_TEXT in entry.get("text", "").lower():
            if _illness_queue is not None:
                _illness_queue.put(True)
    if entry.get("title") == "Protection MHS attempt":
        if cfg.load().get("notifications", {}).get("mhs_protected", False):
            attacker = entry.get("text", "")
            state.push_notification("mhs_protected", f"MHS blocked: {attacker}")
    if entry.get("title") == "REPAIRS":
        if "completed the repairs on your vehicle" in entry.get("text", "").lower():
            if _repair_complete_queue is not None:
                _repair_complete_queue.put(True)


# ---------------------------------------------------------------------------
# Check task (passive, low priority)
# ---------------------------------------------------------------------------

class JournalCheckTask(Task):
    priority = 35
    label = "Journal Check"

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and state.has_new_journals

    def run(self, state: GameState, executor):
        executor.execute(Action("check_journals"), state)


# ---------------------------------------------------------------------------
# Archive task (explicit, triggered from UI queue)
# ---------------------------------------------------------------------------

class ArchiveJournalsTask(Task):
    priority = 5
    label = "Archive Journals"

    def __init__(self, archive_queue: queue.Queue):
        self._queue = archive_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not self._queue.empty()

    def run(self, state: GameState, executor):
        try:
            params = self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("archive_journals", **params), state)


class JournalActionTask(Task):
    priority = 36
    label = "Journal Action"

    def __init__(self, action_queue: queue.Queue):
        self._queue = action_queue

    def can_run(self, state: GameState) -> bool:
        return state.logged_in and not self._queue.empty()

    def run(self, state: GameState, executor):
        try:
            params = self._queue.get_nowait()
        except Exception:
            return
        executor.execute(Action("journal_action", **params), state)
