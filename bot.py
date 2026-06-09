"""
Bot entry point. Builds the scheduler from config and runs the loop.
"""

import threading
import time
import queue
import os
from datetime import datetime
import config as cfg
import paths
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
from tasks.fire_duties import FireDutiesTask
from tasks.drug_manufacturing import DrugManufacturingTask
from tasks.case_work import HospitalCaseWorkTask
from tasks.away_action import AwayActionTask
from tasks.refresh import RefreshTask
from tasks.consume import ConsumeTask
from tasks.check_top_job import CheckTopJobTask
from tasks.snipe_top_job import SnipeTopJobTask
from players import PlayerRefreshTask

_thread: threading.Thread = None
_stop_event = threading.Event()
_pause_event = threading.Event()
_reload_event = threading.Event()
_reload_requested_at: float = 0.0
_RELOAD_DEBOUNCE = 2.0  # seconds
_screenshot_request: queue.Queue = queue.Queue(maxsize=1)
_screenshot_result: queue.Queue = queue.Queue(maxsize=1)
_consume_queue: queue.Queue = queue.Queue()
_clear_earn_event = threading.Event()
state = GameState()


def _transfer_state(old_sched: Scheduler, new_sched: Scheduler):
    """Copy timer/state fields from old tasks to matching new tasks by type."""
    if old_sched is None:
        return
    old_by_type = {type(t): t for t in old_sched._tasks}
    for new_task in new_sched._tasks:
        old = old_by_type.get(type(new_task))
        if old is None:
            continue
        for attr in ("_last_run", "_last_fired", "_last_checked", "_cooldown_until", "_hack_exhausted"):
            if hasattr(old, attr):
                setattr(new_task, attr, getattr(old, attr))


def _build_scheduler(c: dict, old_sched: Scheduler = None) -> Scheduler:
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
        armed = ac.get("armed", {})
        agg_task = AggCrimeTask(
            primary_crime=pri.get("crime", "pickpocket"),
            primary_threshold=pri.get("energy_threshold", 50),
            away_crime=away.get("crime", "pickpocket"),
            away_threshold=away.get("energy_threshold", 50),
            armed_agg_private=armed.get("agg_private", False),
            armed_agg_drug_house=armed.get("agg_drug_house", False),
            armed_payback_private=armed.get("payback_private", False),
            armed_payback_public=armed.get("payback_public", False),
            fallback_to_away=ac.get("fallback_to_away", False),
        )
        agg_task.scheduler = sched
        sched.add(agg_task)

    action_cfg = c.get("action", {})
    if action_cfg.get("enabled", False):
        action_type = action_cfg.get("type", "")
        sub = action_cfg.get("sub_option", "")
        if action_type == "community_service":
            sched.add(CommunityServiceTask())
        elif action_type == "career_training":
            sched.add(CareerTrainingTask(career=sub))
        elif action_type == "fire_duties":
            sched.add(FireDutiesTask())
        elif action_type == "drug_manufacturing":
            sched.add(DrugManufacturingTask())

    cw_cfg = c.get("case_work", {})
    if cw_cfg.get("enabled", False):
        hosp = cw_cfg.get("hospital", {})
        sched.add(HospitalCaseWorkTask(
            poll_interval=hosp.get("poll_interval", 31),
            tasks=hosp.get("tasks", []),
        ))

    away_cfg = c.get("away_action", {})
    if away_cfg.get("enabled", False):
        sched.add(AwayActionTask(action_type=away_cfg.get("type", "drug_manufacturing")))

    sched.add(RefreshTask(interval_seconds=60))
    sched.add(ConsumeTask(_consume_queue))
    sched.add(PlayerRefreshTask())
    sched.add(CheckTopJobTask())
    sched.add(SnipeTopJobTask())

    _transfer_state(old_sched, sched)
    return sched


def _open_log_file() -> object:
    logs_dir = os.path.join(paths.data_dir(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".log"
    return open(os.path.join(logs_dir, filename), "w", encoding="utf-8", buffering=1)


def _run(c: dict):
    global state
    state = GameState()
    state.bot_running = True
    executor = ActionExecutor()
    log_file = _open_log_file()
    _orig_add_log = state.add_log

    def _add_log_with_file(message: str):
        _orig_add_log(message)
        try:
            log_file.write(state.log[-1] + "\n")
        except Exception:
            pass

    state.add_log = _add_log_with_file

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
            if state.logged_in and browser.current_url().rstrip("/") == "https://mafiamatrix.com/default.asp" and not browser.is_cloudflare_challenge():
                state.logged_in = False
                if c.get("misc", {}).get("relog_on_session_expire", True):
                    state.add_log("Session expired — will re-login.")
                else:
                    state.add_log("Session expired — re-login disabled, pausing.")
                    state.relog_suppressed = True
                    _pause_event.set()

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

            # Reload config and rebuild scheduler if Save was pressed (debounced)
            if _reload_event.is_set() and time.monotonic() - _reload_requested_at >= _RELOAD_DEBOUNCE:
                _reload_event.clear()
                c = cfg.load()
                sched = _build_scheduler(c, old_sched=sched)
                state.add_log("Config reloaded.")

            sched.tick(state, executor)

            # Clear earn queue if requested from UI
            if _clear_earn_event.is_set():
                _clear_earn_event.clear()
                executor.execute(Action("clear_earn_queue"), state)

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
            if state.logged_in and c.get("misc", {}).get("logout_on_stop", True):
                state.add_log("Logging out...")
                browser.navigate("https://mafiamatrix.com/default.asp?action=logout")
        except Exception:
            pass
        browser.stop()
        state.bot_running = False
        try:
            log_file.close()
        except Exception:
            pass


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
    state.relog_suppressed = False
    _pause_event.clear()
    state.add_log("Bot resumed.")


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()


def is_paused() -> bool:
    return _pause_event.is_set()


def request_reload():
    global _reload_requested_at
    _reload_requested_at = time.monotonic()
    _reload_event.set()


def request_consume(consume_type: str):
    _consume_queue.put(consume_type)


def request_clear_earn_queue():
    _clear_earn_event.set()


def request_screenshot(timeout: float = 10.0) -> bytes:
    while not _screenshot_result.empty():
        _screenshot_result.get_nowait()
    _screenshot_request.put(True)
    result = _screenshot_result.get(timeout=timeout)
    if isinstance(result, Exception):
        raise result
    return result
