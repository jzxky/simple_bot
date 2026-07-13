"""
Career Crossroad handler.

When the game redirects to /promotion/crossroad.asp, the character must choose
between staying on their current career or switching to a new one. When enabled,
this task detects that page and submits the configured choice:
  - "current" → first radio (current career)
  - "new"     → second radio (new career)

High priority so the crossroad is resolved before other tasks navigate away
(the game keeps redirecting there until it's answered). The note on the page
warns the screen can appear more than once, which is handled naturally: the
task fires again next tick until the page no longer appears.
"""

import config as cfg
import browser
from tasks.base import Task, Action
from state import GameState


class CrossroadTask(Task):
    priority = 90
    label = "Career Crossroad"

    def can_run(self, state: GameState) -> bool:
        if not cfg.load().get("crossroads", {}).get("enabled", False):
            return False
        if not state.logged_in:
            return False
        return "crossroad.asp" in (browser.current_url() or "")

    def run(self, state: GameState, executor):
        selection = cfg.load().get("crossroads", {}).get("selection", "current")
        executor.execute(Action("crossroad", selection=selection), state)
