"""
Makes the pending top job forum post (see promo_post.py) on the main tab.

Runs whenever a post is pending for the logged-in character and the sniper
isn't running (the sniper makes its own attempt first in the side browser).
Out of town, the handler travels home urgently first, turning in warrants that
carry no jail time. After a failed attempt (travel blocked, post not found in
the thread, an error) it tries again after RETRY_SECONDS. The pending record
is on disk, so a restart picks it up too.
"""

import time

import promo_post
from state import GameState
from tasks.base import Task, Action

RETRY_SECONDS = 60


class PromoForumPostTask(Task):
    priority = 98          # below the sniper (99), above auto promo (95)
    label = "Top Job Post"
    changes_city = True

    def __init__(self):
        self._last_try: float = 0.0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail or state.snipe_active:
            return False
        if time.monotonic() - self._last_try < RETRY_SECONDS:
            return False
        return promo_post.pending_for(state) is not None

    def blocked_reasons(self, state):
        reasons = []
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.snipe_active:
            reasons.append("Sniper running")
        if promo_post.pending_for(state) is None:
            reasons.append("No post pending")
        remaining = RETRY_SECONDS - (time.monotonic() - self._last_try)
        if remaining > 0:
            reasons.append(f"Retry in {int(remaining)}s")
        return reasons

    def run(self, state: GameState, executor):
        self._last_try = time.monotonic()
        executor.execute(Action("promo_forum_post"), state)
        if promo_post.pending_for(state) is None:
            self._last_try = 0.0
