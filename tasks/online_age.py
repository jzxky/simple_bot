"""
Tracks character_age and jail_age for known online players.

Every 30 minutes, parses the #whosonlinecell div from the current page to
find who is online. For each known player seen online:
  - If their link class contains "jail" → jail_age += 30
  - Otherwise → character_age += 30

Only runs when logged in and not in jail (bot must be on a page that
renders the online cell, which is all standard game pages).
"""

import re
import time
from bs4 import BeautifulSoup

import browser
import player_db as _db
from tasks.base import Task
from state import GameState

_INTERVAL = 30 * 60  # seconds


class OnlineAgeTask(Task):
    priority = 8
    label = "Online Age Tracker"

    def __init__(self):
        self._last_run: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.in_hospital:
            return False
        return time.monotonic() - self._last_run >= _INTERVAL

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.in_hospital:
            reasons.append("In hospital")
        remaining = _INTERVAL - (time.monotonic() - self._last_run)
        if remaining > 0:
            reasons.append(f"Interval ({int(remaining // 60)}m)")
        return reasons

    def run(self, state: GameState, executor):
        self._last_run = time.monotonic()

        soup = BeautifulSoup(browser.page().content(), "html.parser")
        cell = soup.find("div", id="whosonlinecell", class_=lambda c: c and "global" in c)
        if not cell:
            state.add_log("Online age tracker: #whosonlinecell (global) not found on current page.")
            return

        known = set(_db.get_usernames())
        online_all: set = set()
        jailed: set = set()

        for a in cell.find_all("a", id=re.compile(r"^profileLink:")):
            parts = a["id"].split(":")
            if len(parts) < 2:
                continue
            username = parts[1]
            if username not in known:
                continue
            online_all.add(username)
            if "jail" in a.get("class", []):
                jailed.add(username)

        if not online_all:
            state.add_log("Online age tracker: no known players found online.")
            return

        _db.increment_ages(online_all, jailed, minutes=30)
        state.add_log(
            f"Online age tracker: {len(online_all)} online "
            f"({len(jailed)} jailed, {len(online_all)-len(jailed)} free) — ages updated."
        )
