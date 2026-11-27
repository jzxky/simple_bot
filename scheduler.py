"""
Priority-ordered task scheduler. Each tick, runs the first task whose
can_run() returns True.
"""

import time

from tasks.base import Task

# A task whose own code raises (a parse error, an unexpected page) is cooled
# down instead of ending the run: 30s, then doubling, up to 30 min. A clean run
# resets it.
_ERROR_COOLDOWN_BASE = 30.0
_ERROR_COOLDOWN_MAX = 30 * 60.0


def _is_lost(err) -> bool:
    try:
        import browser
        return browser.is_lost_error(err)
    except Exception:
        return False


class Scheduler:
    def __init__(self):
        self._tasks: list[Task] = []
        # id(task) -> (consecutive failures, cooled down until monotonic time)
        self._errors: "dict[int, tuple[int, float]]" = {}

    def _cooling(self, task) -> float:
        """Seconds left on `task`'s error cooldown (0 when none)."""
        _, until = self._errors.get(id(task), (0, 0.0))
        return max(0.0, until - time.monotonic())

    def _record_error(self, task, state, err, where: str):
        """Log a task's own error and cool it down. A lost browser is re-raised
        so the bot's restart path handles it."""
        if _is_lost(err):
            raise err
        count = self._errors.get(id(task), (0, 0.0))[0] + 1
        wait = min(_ERROR_COOLDOWN_BASE * (2 ** (count - 1)), _ERROR_COOLDOWN_MAX)
        self._errors[id(task)] = (count, time.monotonic() + wait)
        name = task.label or type(task).__name__
        first_line = (str(err).strip().splitlines() or [type(err).__name__])[0][:300]
        state.add_log(f"{name} failed ({where}): {first_line} — skipping it for {int(wait)}s.")
        try:
            import crash_report
            crash_report.capture("task_error", err, state, f"{name} ({where})", with_page=False)
        except Exception:
            pass

    def inherit_errors(self, old: "Scheduler"):
        """Carry error cooldowns over from the scheduler this one replaces
        (matched by task type), so a config save doesn't retry a failing task
        at once."""
        by_type = {type(t): old._errors[id(t)] for t in old._tasks if id(t) in old._errors}
        for task in self._tasks:
            err = by_type.get(type(task))
            if err is not None:
                self._errors[id(task)] = err

    def add(self, task: Task):
        self._tasks.append(task)
        self._tasks.sort(key=lambda t: t.priority, reverse=True)

    def tick(self, state, executor):
        # Why a task isn't running is shown in the Scheduler panel
        # (snapshot()), so per-tick skip/blocked lines aren't logged here.
        for task in self._tasks:
            if state.in_hospital and not task.run_in_hospital:
                continue
            if state.agg_tab_active and task.changes_city:
                continue
            if state.drug_tab_active and (task.changes_city or task.moves_cash):
                continue
            if self._cooling(task):
                continue
            try:
                ready = task.can_run(state)
            except Exception as e:
                self._record_error(task, state, e, "check")
                continue
            if ready:
                state.current_task = task.label or type(task).__name__
                try:
                    task.run(state, executor)
                except Exception as e:
                    self._record_error(task, state, e, "run")
                else:
                    self._errors.pop(id(task), None)
                finally:
                    state.current_task = ""
                return

    def snapshot(self, state) -> list[dict]:
        """Return current can_run status and blocking reasons for all tasks."""
        result = []
        for task in self._tasks:
            reasons = []
            if state.in_hospital and not task.run_in_hospital:
                reasons.append("In hospital")
            if state.agg_tab_active and task.changes_city:
                reasons.append("Crime tab active")
            if state.drug_tab_active and (task.changes_city or task.moves_cash):
                reasons.append("Drug window busy")
            cooling = self._cooling(task)
            if cooling:
                reasons.append(f"Error cooldown ({int(cooling)}s)")
            try:
                reasons.extend(task.blocked_reasons(state))
            except Exception:
                reasons.append("Error checking guards")
            ready = len(reasons) == 0
            result.append({
                "label": task.label or type(task).__name__,
                "priority": task.priority,
                "ready": ready,
                "reasons": reasons,
            })
        return result
