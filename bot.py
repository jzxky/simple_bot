"""
Bot entry point. Builds the scheduler from config and runs the loop.
"""

import threading
import time
import queue
import config as cfg
import browser
from state import GameState
from scheduler import Scheduler
from executor import ActionExecutor
from tasks.base import Action
from tasks.login import LoginTask
from tasks.earns import EarnsTask
from tasks.agg_crimes import AggCrimeTask
from tasks.community_service import CommunityServiceTask
from tasks.career_training import CareerTrainingTask
from tasks.away_action import AwayActionTask
from tasks.refresh import RefreshTask

_thread: threading.Thread = None
_stop_event = threading.Event()
_pause_event = threading.Event()
_reload_event = threading.Event()
_screenshot_request: queue.Queue = queue.Queue(maxsize=1)
_screenshot_result: queue.Queue = queue.Queue(maxsize=1)
state = GameState()


def _build_scheduler(c: dict) -> Scheduler:
    sched = Scheduler()

    creds = c.get("credentials", {})
    sched.add(LoginTask(creds.get("email", ""), creds.get("password", "")))

    if c.get("earns", {}).get("enabled", False):
        earn_cfg = c["earns"]
        sched.add(EarnsTask(
            earn_type=earn_cfg.get("earn_type", "surgeon"),
            interval_minutes=earn_cfg.get("check_interval_minutes", 30),
        ))

    if c.get("aggravated_crimes", {}).get("enabled", False):
        ac = c["aggravated_crimes"]
        pri = ac.get("primary", {})
        away = ac.get("away_crime", {})
        sched.add(AggCrimeTask(
            primary_crime=pri.get("crime", "pickpocket"),
            primary_threshold=pri.get("energy_threshold", 50),
            away_crime=away.get("crime", "pickpocket"),
            away_threshold=away.get("energy_threshold", 50),
        ))

    action_cfg = c.get("action", {})
    if action_cfg.get("enabled", False):
        action_type = action_cfg.get("type", "")
        sub = action_cfg.get("sub_option", "")
        if action_type == "community_service":
            sched.add(CommunityServiceTask())
        elif action_type == "career_training":
            sched.add(CareerTrainingTask(career=sub))

    away_cfg = c.get("away_action", {})
    if away_cfg.get("enabled", False):
        sched.add(AwayActionTask(action_type=away_cfg.get("type", "drug_manufacturing")))

    sched.add(RefreshTask(interval_seconds=60))

    return sched


def _run(c: dict):
    global state
    state = GameState()
    state.bot_running = True
    executor = ActionExecutor()

    try:
        state.add_log("Starting browser...")
        browser.start()
        state.add_log("Browser started.")
    except Exception as e:
        state.add_log(f"Browser failed to start: {e}")
        state.last_error = str(e)
        state.bot_running = False
        return

    try:
        sched = _build_scheduler(c)

        while not _stop_event.is_set():
            if _pause_event.is_set():
                time.sleep(1)
                continue

            # Detect Cloudflare challenge — pause and wait for manual resolution
            if browser.is_cloudflare_challenge():
                state.add_log(
                    "Cloudflare gateway detected — manual takeover required. "
                    "Complete the challenge in the browser then press Resume."
                )
                _pause_event.set()
                continue

            # Detect session expiry on every tick
            if state.logged_in and "default.asp" in browser.current_url() and not browser.is_cloudflare_challenge():
                state.logged_in = False
                state.add_log("Session expired — will re-login.")

            # Screenshot requests from the Flask thread
            if not _screenshot_request.empty():
                try:
                    _screenshot_request.get_nowait()
                    png = browser.page().screenshot(full_page=True)
                    _screenshot_result.put(png)
                except Exception as e:
                    _screenshot_result.put(e)

            if _stop_event.is_set():
                break

            # Reload config and rebuild scheduler if Save was pressed
            if _reload_event.is_set():
                _reload_event.clear()
                c = cfg.load()
                sched = _build_scheduler(c)
                state.add_log("Config reloaded.")

            sched.tick(state, executor)

            # Payback after a successful crime
            if getattr(state, "_last_crime_victim", None) and c.get("payback_enabled", False):
                executor.execute(
                    Action("payback", amount=state._last_crime_amount, target=state._last_crime_victim),
                    state,
                )
                del state._last_crime_victim
                del state._last_crime_amount

            time.sleep(2)

    except Exception as e:
        state.add_log(f"Bot crashed: {e}")
    finally:
        try:
            if state.logged_in:
                state.add_log("Logging out...")
                browser.navigate("https://mafiamatrix.com/default.asp?action=logout")
        except Exception:
            pass
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


def request_reload():
    _reload_event.set()


def request_screenshot(timeout: float = 10.0) -> bytes:
    while not _screenshot_result.empty():
        _screenshot_result.get_nowait()
    _screenshot_request.put(True)
    result = _screenshot_result.get(timeout=timeout)
    if isinstance(result, Exception):
        raise result
    return result
