"""
Aggravated crime task.

Primary crime is always attempted when in home city (or for non-home-city crimes, anywhere).
Away crime is only configured when primary is 'hack' and is attempted when not in home city.
Armed robbery loops indefinitely — after each 12-retry pass with no targets it checks whether
any other task (except consume) is ready; if so it yields, otherwise it retries immediately.

Separate-tab mode (config: aggravated_crimes.separate_tab): instead of running the crime
loop inline on the main tab — which blocks every other task until it returns — this task
opens a second browser tab and drives it one step per bot-loop tick via tick_agg(), the
same cooperative pattern tasks/snipe_top_job.py uses for its own second tab. Each of the
executor's crime handlers is available in generator form (see executor._do_crime_steps,
_breaking_entering_steps, _armed_robbery_steps, _torch_business_steps) — they yield once
per target/attempt instead of running the whole loop in one call, so sched.tick() and every
other ready task get serviced on the main tab within one loop iteration (~2s) instead of
waiting for the entire crime run to finish.
"""

import time
import browser
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
                 fallback_to_away: bool = False,
                 torch_private: bool = False,
                 torch_payback_public: str = "everyone",
                 torch_payback_private: str = "everyone",
                 separate_tab: bool = False):
        self.primary_crime = primary_crime
        self.primary_threshold = primary_threshold
        self.away_crime = away_crime
        self.away_threshold = away_threshold
        self.armed_agg_private = armed_agg_private
        self.armed_agg_drug_house = armed_agg_drug_house
        self.fallback_to_away = fallback_to_away
        self.torch_private = torch_private
        self.torch_payback_public = torch_payback_public
        self.torch_payback_private = torch_payback_private
        self.separate_tab = separate_tab
        self._cooldown_until: float = 0.0
        self._hack_exhausted: bool = False
        self.scheduler = None  # set by bot.py after scheduler is built

        # Separate-tab run state
        self._page = None
        self._gen = None
        self._active_crime: "str | None" = None
        self._active_threshold: int = 0

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
        if state.agg_tab_active or state.snipe_active:
            return False
        if not state.logged_in or state.in_jail:
            return False
        if state.cs_sentence > 0:
            return False
        # Back off aggravated crimes once fails hit the 30-min-window threshold.
        if state.agg_fail_count() >= 3:
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

    def blocked_reasons(self, state):
        reasons = []
        if state.agg_tab_active:
            reasons.append("Crime tab already running")
        if state.snipe_active:
            reasons.append("Snipe tab active")
        if not state.logged_in:
            reasons.append("Not logged in")
        if state.in_jail:
            reasons.append("In jail")
        if state.cs_sentence > 0:
            reasons.append("CS sentence active")
        if state.agg_fail_count() >= 3:
            reasons.append("Too many agg fails")
        remaining = self._cooldown_until - time.monotonic()
        if remaining > 0:
            reasons.append(f"Cooldown ({int(remaining)}s)")
        crime, _ = self._pick_crime(state)
        if crime is None:
            reasons.append("No crime available")
        elif crime == "armed" and "gangster" not in state.occupation.lower() and not state.action_available():
            reasons.append("Action timer busy (armed robbery)")
        return reasons

    def run(self, state: GameState, executor):
        crime, threshold = self._pick_crime(state)
        if not crime:
            return

        if self.separate_tab:
            self._launch_tab(state, crime, threshold)
            return

        if crime == "armed":
            executor.execute(Action("do_armed_robbery",
                threshold=threshold,
                agg_private=self.armed_agg_private,
                agg_drug_house=self.armed_agg_drug_house,
                check_other_tasks=lambda: self._other_task_ready(state),
            ), state)
        elif crime == "torch":
            executor.execute(Action("do_torch_business",
                threshold=threshold,
                torch_private=self.torch_private,
                torch_payback_public=self.torch_payback_public,
                torch_payback_private=self.torch_payback_private,
                check_other_tasks=lambda: self._other_task_ready(state),
            ), state)
        else:
            executor.execute(Action("do_crime", crime=crime, threshold=threshold), state)

        self._handle_post_run(state)

    def _handle_post_run(self, state: GameState):
        """Shared by both the inline path (called right after the crime action
        completes) and the separate-tab path (called once its generator ends) —
        applies the exhaustion cooldown / hack-fallback bookkeeping identically
        either way."""
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

    # ------------------------------------------------------------------
    # Separate-tab mode
    # ------------------------------------------------------------------

    def _build_action(self, crime: str, threshold: int) -> Action:
        if crime == "armed":
            return Action("do_armed_robbery",
                threshold=threshold,
                agg_private=self.armed_agg_private,
                agg_drug_house=self.armed_agg_drug_house,
            )
        if crime == "torch":
            return Action("do_torch_business",
                threshold=threshold,
                torch_private=self.torch_private,
                torch_payback_public=self.torch_payback_public,
                torch_payback_private=self.torch_payback_private,
            )
        return Action("do_crime", crime=crime, threshold=threshold)

    @staticmethod
    def _build_generator(action: Action, state: GameState):
        import executor
        if action.kind == "do_armed_robbery":
            return executor._armed_robbery_steps(action, state)
        if action.kind == "do_torch_business":
            return executor._torch_business_steps(action, state)
        return executor._do_crime_steps(action, state)

    def _launch_tab(self, state: GameState, crime: str, threshold: int):
        try:
            page = browser.new_page()
        except Exception as e:
            state.add_log(f"Agg Crimes: failed to open tab: {e}")
            return

        action = self._build_action(crime, threshold)
        self._page = page
        self._gen = self._build_generator(action, state)
        self._active_crime = crime
        self._active_threshold = threshold
        state.agg_tab_active = True
        state.agg_tab_crime = crime
        state.add_log(f"Agg Crimes: launching '{crime}' in a new tab.")

    def _stop_reason(self, state: GameState) -> "str | None":
        """Re-check the same launch conditions can_run() would; return why the
        tab run should stop now, or None to keep going."""
        if not state.logged_in:
            return "logged out"
        if state.in_jail:
            return "in jail"
        if state.in_hospital:
            return "in hospital"
        if state.cs_sentence > 0:
            return "CS sentence issued"
        if state.agg_fail_count() >= 3:
            return "too many agg fails"
        crime, _ = self._pick_crime(state)
        if crime != self._active_crime:
            return "conditions changed" if crime is None else "crime selection changed"
        if self._active_threshold and state.energy < self._active_threshold:
            return "energy dropped below threshold"
        return None

    def tick_agg(self, state: GameState):
        """Called once per bot-loop iteration while state.agg_tab_active — advances
        the crime tab's generator by exactly one step."""
        import bot as _bot

        if _bot._cancel_agg_event.is_set():
            _bot._cancel_agg_event.clear()
            self._finish_agg(state, reason="cancelled")
            return

        if _bot._stop_event.is_set():
            self._finish_agg(state, reason="bot stopping")
            return

        reason = self._stop_reason(state)
        if reason:
            self._finish_agg(state, reason=reason)
            return

        saved_html, saved_url = state.page_html, state.current_url
        try:
            with browser.use_page(self._page):
                next(self._gen)
        except StopIteration:
            self._handle_post_run(state)
            self._finish_agg(state, reason="run finished")
            return
        except Exception as e:
            state.add_log(f"Agg Crimes (tab): error — {e}")
            self._finish_agg(state, reason="error")
            return
        finally:
            # Between ticks, state.page_html/current_url must keep describing the
            # main tab — many unrelated handlers read them assuming that.
            state.page_html, state.current_url = saved_html, saved_url

    def _finish_agg(self, state: GameState, reason: str = ""):
        if self._gen is not None:
            try:
                self._gen.close()
            except Exception:
                pass
            self._gen = None
        if self._page is not None:
            browser.close_page(self._page)
            self._page = None
        state.agg_tab_active = False
        state.agg_tab_crime = ""
        self._active_crime = None
        self._active_threshold = 0
        if reason:
            state.add_log(f"Agg Crimes: tab closed ({reason}).")

    def stop_tab(self, state: GameState):
        """External request to abandon the current tab run immediately (e.g. a
        manual travel request, or the scheduler being rebuilt on config save)."""
        if self._gen is not None or self._page is not None:
            self._finish_agg(state, reason="stopped")
