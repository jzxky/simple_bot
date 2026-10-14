"""
Aggravated crime task.

Primary crime is always attempted when in home city (or for non-home-city crimes, anywhere).
Away crime is only configured when primary is 'hack' and is attempted when not in home city.
Armed robbery loops indefinitely — after each 12-retry pass with no targets it checks whether
any other task (except consume) is ready; if so it yields, otherwise it retries immediately.

Separate-tab mode (config: aggravated_crimes.separate_tab): instead of running the crime
loop inline on the main tab — which blocks every other task until it returns — this task
hands the run to the side browser's "crime" lane (side_browser.py): a separate patchright
instance on its own thread, independent of the top-job sniper's lane. It opens a new tab there and runs the executor's crime routine (generator forms:
executor._do_crime_steps, _breaking_entering_steps, _armed_robbery_steps,
_torch_business_steps) back to back with no gaps, exactly like inline mode, until the
targets run out or there's a success/fail result; then it closes the tab. Between targets
it re-checks the stop conditions (cancel, bot stop, jail, hospital, CS sentence, too many
fails, energy/crime selection change, or — for armed robbery only, since a failed armed
robbery can hospitalise the character — a top-job snipe starting).

The run works on its own copy of the GameState so the side tab's page parses never
overwrite the main tab's page_html/current_url; the relevant results (energy, money, jail,
timers, agg fails, payback victim, targets-exhausted) are copied back when it ends.
"""

import copy
import time
import browser
import side_browser
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

        # Separate-tab run (side browser job) in flight, if any
        self._job = None

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
        if state.agg_tab_active:
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
        # A failed armed robbery can hospitalise the character, which would
        # wreck a top-job snipe in progress. Other crimes run alongside it.
        if crime == "armed" and state.snipe_active:
            return False
        # Non-gangsters using armed robbery consume the action timer; skip if it's not free
        if crime == "armed" and "gangster" not in state.occupation.lower() and not state.action_available():
            return False
        return True

    def blocked_reasons(self, state):
        reasons = []
        if state.agg_tab_active:
            reasons.append("Crime tab already running")
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
        elif crime == "armed" and state.snipe_active:
            reasons.append("Top-job snipe active (armed robbery)")
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
        import bot as _bot
        action = self._build_action(crime, threshold)
        _bot._cancel_agg_event.clear()  # a stale cancel click mustn't kill this run
        state.agg_tab_active = True
        state.agg_tab_crime = crime
        state.add_log(f"Agg Crimes: launching '{crime}' in the side browser.")
        headless = cfg.load().get("misc", {}).get("headless", False)
        self._job = side_browser.submit(
            "crime", f"agg:{crime}",
            lambda side, job: self._run_job(side, job, state, action, crime, threshold),
            cookies=browser.export_cookies(), headless=headless,
        )

    def _stop_reason(self, state: GameState, crime: str, threshold: int) -> "str | None":
        """Re-check the same launch conditions can_run() would; return why the
        run should stop now, or None to keep going."""
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
        picked, _ = self._pick_crime(state)
        if picked != crime:
            return "conditions changed" if picked is None else "crime selection changed"
        if threshold and state.energy < threshold:
            return "energy dropped below threshold"
        return None

    # ------------------------------------------------------------------
    # Worker thread
    # ------------------------------------------------------------------

    @staticmethod
    def _shadow_state(state: GameState) -> GameState:
        """A copy of `state` for the side tab to parse into. Logs and
        notifications still go to the real state."""
        shadow = copy.copy(state)
        shadow.agg_fail_times = list(state.agg_fail_times)
        shadow.timers = dict(state.timers)
        shadow.add_log = lambda msg: state.add_log(f"[Side] {msg}")
        shadow.push_notification = state.push_notification
        for attr in ("_last_crime_victim", "_last_crime_amount",
                     "_last_crime_payback_mode", "_agg_targets_exhausted"):
            shadow.__dict__.pop(attr, None)
        return shadow

    @staticmethod
    def _merge_back(state: GameState, shadow: GameState, fails_before: list):
        """Copy the run's results from the shadow state onto the real one."""
        for t in shadow.agg_fail_times:
            if t not in fails_before:
                state.agg_fail_times.append(t)
        for attr in ("energy", "clean_money", "dirty_money", "in_jail", "in_hospital",
                     "hospital_release_at", "cs_sentence", "jail_release_secs"):
            setattr(state, attr, getattr(shadow, attr))
        if shadow.timers:
            state.timers = shadow.timers
            state.action_timer_ready = shadow.action_timer_ready
            state.action_timer_end = shadow.action_timer_end
            state.agg_pro_active = shadow.agg_pro_active
            state.agg_pro_end = shadow.agg_pro_end
        if getattr(shadow, "_agg_targets_exhausted", False):
            state._agg_targets_exhausted = True
        if getattr(shadow, "_last_crime_victim", None):
            # The main loop pays back as soon as it sees _last_crime_victim, so
            # set the amount (and mode) first.
            state._last_crime_amount = shadow._last_crime_amount
            if hasattr(shadow, "_last_crime_payback_mode"):
                state._last_crime_payback_mode = shadow._last_crime_payback_mode
            state._last_crime_victim = shadow._last_crime_victim

    def _run_job(self, side, job, state: GameState, action: Action, crime: str, threshold: int):
        import bot as _bot
        shadow = self._shadow_state(state)
        fails_before = list(state.agg_fail_times)
        pg = None
        reason = "run finished"
        finished = False
        try:
            if crime == "armed" and state.snipe_active:
                reason = "top-job snipe active"
                return
            pg = side.new_page(job)
            with browser.use_page(pg):
                gen = self._build_generator(action, shadow)
                try:
                    for _ in gen:
                        if _bot._cancel_agg_event.is_set():
                            _bot._cancel_agg_event.clear()
                            reason = "cancelled"
                            break
                        if job.cancel.is_set():
                            reason = job.cancel_reason or "stopped"
                            break
                        if crime == "armed" and state.snipe_active:
                            reason = "top-job snipe started"
                            break
                        stop = self._stop_reason(shadow, crime, threshold)
                        if stop:
                            reason = stop
                            break
                    else:
                        finished = True
                finally:
                    gen.close()
        except Exception as e:
            state.add_log(f"Agg Crimes (side): error — {e}")
            reason = "error"
        finally:
            if pg is not None:
                side.close_page(pg)
            try:
                self._merge_back(state, shadow, fails_before)
                if finished:
                    self._handle_post_run(state)
            finally:
                # Last, so the scheduler can't relaunch before the cooldown is set.
                state.agg_tab_active = False
                state.agg_tab_crime = ""
                state.add_log(f"Agg Crimes: side tab closed ({reason}).")

    def stop_tab(self, state: GameState, wait: float = 10.0):
        """Main thread: abandon the current run (e.g. a manual travel request,
        or the scheduler being rebuilt on config save) and wait up to `wait`
        seconds for it to wind down — it stops at its next target."""
        job = self._job
        if job is None or job.done.is_set():
            return
        job.request_cancel("stopped")
        job.done.wait(wait)
