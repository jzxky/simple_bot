"""
Aggravated crime task.

Primary crime is always attempted when in home city (or for non-home-city crimes, anywhere).
Away crime is only configured when primary is 'hack' and is attempted when not in home city.
Armed robbery loops indefinitely — after each 12-retry pass with no targets it checks whether
any other task (except consume) is ready; if so it yields, otherwise it retries immediately.
"""

import time
import config as cfg
from tasks.base import Task, Action
from state import GameState

HACK_CRIME = "hack"
COOLDOWN_SECONDS = 180


class AggCrimeTask(Task):
    priority = 50
    label = 'Agg Crimes'

    def __init__(self, primary_crime: str, primary_threshold: int,
                 away_crime: str, away_threshold: int,
                 armed_agg_private: bool = False, armed_agg_drug_house: bool = False,
                 fallback_to_away: bool = False):
        self.primary_crime = primary_crime
        self.primary_threshold = primary_threshold
        self.away_crime = away_crime
        self.away_threshold = away_threshold
        self.armed_agg_private = armed_agg_private
        self.armed_agg_drug_house = armed_agg_drug_house
        self.fallback_to_away = fallback_to_away
        self._cooldown_until: float = 0.0
        self._hack_exhausted: bool = False
        self.scheduler = None  # set by bot.py after scheduler is built

    def _other_task_ready(self, state: GameState) -> bool:
        """Return True if any task other than self or ConsumeTask can run."""
        if self.scheduler is None:
            return False
        from tasks.consume import ConsumeTask
        for task in self.scheduler._tasks:
            if task is self:
                continue
            if isinstance(task, ConsumeTask):
                continue
            if task.can_run(state):
                return True
        return False

    def _pick_crime(self, state: GameState):
        if self.primary_crime == HACK_CRIME:
            if not state.in_home_city():
                if self.away_crime and state.energy >= self.away_threshold:
                    return self.away_crime, self.away_threshold
                return None, 0
            if not self._hack_exhausted:
                if state.energy >= self.primary_threshold:
                    return self.primary_crime, self.primary_threshold
                return None, 0
            if self.fallback_to_away and self.away_crime and state.energy >= self.away_threshold:
                return self.away_crime, self.away_threshold
            return None, 0
        if state.energy >= self.primary_threshold:
            return self.primary_crime, self.primary_threshold
        return None, 0

    def can_run(self, state: GameState) -> bool:
        if not state.logged_in or state.in_jail:
            return False
        if state.cs_sentence > 0:
            return False
        if time.monotonic() < self._cooldown_until:
            return False
        crime, _ = self._pick_crime(state)
        if crime is None:
            return False
        # Non-gangsters using armed robbery consume the action timer; skip if it's not free
        if crime == "armed" and "gangster" not in state.occupation.lower() and not state.action_available():
            return False
        return True

    def run(self, state: GameState, executor):
        crime, threshold = self._pick_crime(state)
        if not crime:
            return

        if crime == "armed":
            executor.execute(Action("do_armed_robbery",
                threshold=threshold,
                agg_private=self.armed_agg_private,
                agg_drug_house=self.armed_agg_drug_house,
                check_other_tasks=lambda: self._other_task_ready(state),
            ), state)
        else:
            executor.execute(Action("do_crime", crime=crime, threshold=threshold), state)

        if getattr(state, "_agg_targets_exhausted", False):
            state._agg_targets_exhausted = False

            if (self.primary_crime == HACK_CRIME and self.fallback_to_away
                    and self.away_crime and state.in_home_city()):
                if not self._hack_exhausted:
                    self._hack_exhausted = True
                    state.add_log("Hack targets exhausted — falling back to away crime.")
                else:
                    self._hack_exhausted = False
                    self._cooldown_until = time.monotonic() + COOLDOWN_SECONDS
                    msg = "All targets exhausted — 3 minute cooldown started."
                    state.add_log(msg)
                    if cfg.load().get("notifications", {}).get("targets_exhausted", False):
                        state.push_notification("targets_exhausted", msg)
            else:
                self._cooldown_until = time.monotonic() + COOLDOWN_SECONDS
                msg = "All targets exhausted — 3 minute cooldown started."
                state.add_log(msg)
                if cfg.load().get("notifications", {}).get("targets_exhausted", False):
                    state.push_notification("targets_exhausted", msg)
        elif self._hack_exhausted:
            self._hack_exhausted = False
