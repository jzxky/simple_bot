"""
Bot entry point. Builds the scheduler from config and runs the loop.
"""

import threading
import time
import queue
import config as cfg
import browser
from state import GameState, parse_state
from scheduler import Scheduler
from executor import ActionExecutor
from tasks.login import LoginTask
from tasks.earns import EarnsTask
from tasks.agg_crimes import AggCrimeTask
from tasks.community_service import CommunityServiceTask
from tasks.career_training import CareerTrainingTask

_thread: threading.Thread = None
_stop_event = threading.Event()
_pause_event = threading.Event()
_screenshot_request: queue.Queue = queue.Queue(maxsize=1)
_screenshot_result: queue.Queue = queue.Queue(maxsize=1)
state = GameState()


def _build_scheduler(c: dict) -> Scheduler:
    sched = Scheduler(tick_interval=2.0)

    creds = c.get("credentials", {})
    sched.add(LoginTask(creds.get("email", ""), creds.get("password", "")))

    if c.get("earns", {}).get("enabled", False):
        earn_cfg = c["earns"]
        sched.add(EarnsTask(
            earn_type=earn_cfg.get("earn_type", "surgeon"),
            interval_minutes=earn_cfg.get("check_interval_minutes", 30)
        ))

    if c.get("aggravated_crimes", {}).get("enabled", False):
        ac = c["aggravated_crimes"]
        pri = ac.get("primary", {})
        sec = ac.get("secondary", {})
        sched.add(AggCrimeTask(
            primary_crime=pri.get("crime", "pickpocket"),
            primary_threshold=pri.get("energy_threshold", 50),
            secondary_crime=sec.get("crime", "pickpocket"),
            secondary_threshold=sec.get("energy_threshold", 50),
        ))

    action_cfg = c.get("action", {})
    if action_cfg.get("enabled", False):
        action_type = action_cfg.get("type", "")
        sub = action_cfg.get("sub_option", "")
        if action_type == "community_service":
            sched.add(CommunityServiceTask())
        elif action_type == "career_training":
            sched.add(CareerTrainingTask(career=sub or c.get("career_training", {}).get("career", "fire")))

    return sched


def _run(c: dict):
    global state
    state = GameState()
    state.bot_running = True
    executor = ActionExecutor()

    # Start browser — stop immediately on Chrome not found
    try:
        state.add_log("Starting browser...")
        browser.start()
        state.add_log("Browser started.")
    except browser.ChromeNotFoundError as e:
        state.add_log(f"ERROR: {e}")
        state.add_log("Download Chrome from https://www.google.com/chrome or set a custom path in Bot Config settings.")
        state.last_error = str(e)
        state.bot_running = False
        return
    except Exception as e:
        state.add_log(f"Browser failed to start: {e}")
        state.last_error = str(e)
        state.bot_running = False
        return

    # Main loop
    try:
        sched = _build_scheduler(c)

        while not _stop_event.is_set():
            if _pause_event.is_set():
                time.sleep(1)
                continue

            # Check for session expiry on every tick
            if state.logged_in and "default.asp" in browser.current_url():
                state.logged_in = False

            # Handle screenshot requests from the Flask thread
            if not _screenshot_request.empty():
                try:
                    _screenshot_request.get_nowait()
                    png = browser.page().screenshot(full_page=True)
                    _screenshot_result.put(png)
                except Exception as e:
                    _screenshot_result.put(e)

            sched.tick(state, executor)

            # Reset one-shot action-timer tasks so they fire again next cycle
            for task in list(sched._tasks):
                if task.is_complete and hasattr(task, "condition"):
                    task.is_complete = False
                    sched._tasks = [t for t in sched._tasks if not (t.is_complete and not hasattr(t, "condition"))]

            # Handle payback after a successful crime
            if hasattr(state, "_last_crime_victim") and c.get("payback_enabled", False):
                from tasks.base import Action
                executor.execute(
                    Action("payback", amount=state._last_crime_amount, target=state._last_crime_victim),
                    state
                )
                del state._last_crime_victim
                del state._last_crime_amount

            time.sleep(sched.tick_interval)

    except Exception as e:
        state.add_log(f"Bot crashed: {e}")
    finally:
        browser.stop()
        state.bot_running = False


def start():
    global _thread, _stop_event
    if _thread and _thread.is_alive():
        return
    _stop_event.clear()
    _pause_event.clear()
    c = cfg.load()
    _thread = threading.Thread(target=_run, args=(c,), daemon=True)
    _thread.start()


def stop():
    _stop_event.set()
    _pause_event.clear()


def pause():
    _pause_event.set()
    state.add_log("Bot paused.")


def resume():
    _pause_event.clear()
    state.add_log("Bot resumed.")


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def is_paused() -> bool:
    return _pause_event.is_set()


def request_screenshot(timeout: float = 10.0) -> bytes:
    """Ask the bot thread to take a screenshot. Blocks until done or timeout."""
    # Clear any stale results
    while not _screenshot_result.empty():
        _screenshot_result.get_nowait()
    _screenshot_request.put(True)
    result = _screenshot_result.get(timeout=timeout)
    if isinstance(result, Exception):
        raise result
    return result
