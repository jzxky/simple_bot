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

def _journals_path(char_name: str) -> Path:
    from paths import data_dir
    return Path(data_dir()) / f"journals_{char_name}.json"


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
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_label(label) -> tuple[str, str, str]:
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


def _parse_journal_rows(soup) -> list[dict]:
    """Return list of dicts with id/title/time/text for every journal_row on the page."""
    entries = []
    for row in soup.find_all("tr", class_="journal_row"):
        td = row.find("td", class_="journal_event")
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
    """Return True if the journal_row immediately follows a NEW marker tr."""
    prev = row_tag.find_previous_sibling("tr")
    if prev:
        cell = prev.find("td", id="comms_msg_top_super")
        if cell:
            return True
    return False


def _new_entries_on_page(soup) -> list[dict]:
    """Return only the NEW-flagged entries on this page."""
    new = []
    for row in soup.find_all("tr", class_="journal_row"):
        if _has_new_marker_before(soup, row):
            td = row.find("td", class_="journal_event")
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


def _next_page_url(soup) -> str | None:
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if re.search(r"journal\.asp\?p=\d+", href) and a.get_text(strip=True) == "Next":
            if href.startswith("http"):
                return href
            return _urls.BASE_URL + "/journal/" + href
    return None


_drug_trade_queue: "queue.Queue | None" = None
_illness_queue: "queue.Queue | None" = None

_FLU_TEXT = "you have a slightly nauseous feeling in your stomach"


def set_drug_trade_queue(q: "queue.Queue"):
    global _drug_trade_queue
    _drug_trade_queue = q


def set_illness_queue(q: "queue.Queue"):
    global _illness_queue
    _illness_queue = q


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
