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
import urls
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
from tasks.case_work import HospitalCaseWorkTask, EngineeringCaseWorkTask
from tasks.away_action import AwayActionTask
from tasks.refresh import RefreshTask
from tasks.consume import ConsumeTask
from tasks.check_top_job import CheckTopJobTask
from tasks.snipe_top_job import SnipeTopJobTask
from tasks.auto_promo import AutoPromoTask
from tasks.jail_duties import JailDutiesTask
from tasks.jail_action import JailActionTask
from tasks.jail_consume import JailConsumeTask
from tasks.deposit import DepositTask
from tasks.withdraw import WithdrawTask
from tasks.maintain_cash import MaintainCashTask
from tasks.character_history import CharacterHistoryTask
from tasks.jailbreak import PlanJailBreakTask, ExecuteJailBreakTask, CallOffJailBreakTask
from tasks.journal import JournalCheckTask, ArchiveJournalsTask, set_drug_trade_queue, set_illness_queue
from tasks.drug_trade import DrugTradeTask
from tasks.illness import IllnessTask
from tasks.gym import GymTask
from tasks.casino import CasinoTask
from tasks.respect import RespectTask
from tasks.cs_punishment import CSPunishmentTask
from tasks.online_age import OnlineAgeTask
from tasks.bionics import BionicsTask
from players import PlayerRefreshTask, SyncTask

_thread: threading.Thread = None
_bionics_task = None
_scheduler_snapshot: list = []
_sched: "Scheduler | None" = None
_state: "GameState | None" = None
_stop_event = threading.Event()
_pause_event = threading.Event()
_reload_event = threading.Event()
_reload_requested_at: float = 0.0
_RELOAD_DEBOUNCE = 2.0  # seconds
_consume_queue: queue.Queue = queue.Queue()
_deposit_queue: queue.Queue = queue.Queue()
_withdraw_queue: queue.Queue = queue.Queue()
_char_history_queue: queue.Queue = queue.Queue()
_jailbreak_plan_queue: queue.Queue = queue.Queue()
_jailbreak_execute_queue: queue.Queue = queue.Queue()
_jailbreak_calloff_queue: queue.Queue = queue.Queue()
_archive_journals_queue: queue.Queue = queue.Queue()
_drug_trade_queue: queue.Queue = queue.Queue()
set_drug_trade_queue(_drug_trade_queue)
_illness_queue: queue.Queue = queue.Queue()
set_illness_queue(_illness_queue)
_jail_inmates_request: queue.Queue = queue.Queue(maxsize=1)
_jail_inmates_result: queue.Queue = queue.Queue(maxsize=1)
_warrants_request: queue.Queue = queue.Queue(maxsize=1)
_warrants_result: queue.Queue = queue.Queue(maxsize=1)
_turn_in_warrant_queue: queue.Queue = queue.Queue()
_travel_queue: queue.Queue = queue.Queue()
_travel_dests_request: queue.Queue = queue.Queue(maxsize=1)
_travel_dests_result: queue.Queue = queue.Queue(maxsize=1)
_clear_earn_event = threading.Event()
_clear_jail_duty_queue_event = threading.Event()
_respect_refresh_queue: queue.Queue = queue.Queue()
_bar_threads_request: queue.Queue = queue.Queue(maxsize=1)
_bar_threads_result: queue.Queue = queue.Queue(maxsize=1)
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
            fallback_to_away=ac.get("fallback_to_away", False),
        )
        agg_task.scheduler = sched
        sched.add(agg_task)
        sched.add(CSPunishmentTask())

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
        eng = cw_cfg.get("engineering", {})
        sched.add(EngineeringCaseWorkTask(poll_interval=eng.get("poll_interval", 31), tasks=eng.get("tasks", [])))

    away_cfg = c.get("away_action", {})
    if away_cfg.get("enabled", False):
        sched.add(AwayActionTask(action_type=away_cfg.get("type", "drug_manufacturing")))

    sched.add(RefreshTask(interval_seconds=60))
    sched.add(ConsumeTask(_consume_queue))
    sched.add(DepositTask(_deposit_queue))
    sched.add(WithdrawTask(_withdraw_queue))
    sched.add(MaintainCashTask())
    sched.add(CharacterHistoryTask(_char_history_queue))
    sched.add(PlanJailBreakTask(_jailbreak_plan_queue))
    sched.add(ExecuteJailBreakTask(_jailbreak_execute_queue))
    sched.add(CallOffJailBreakTask(_jailbreak_calloff_queue))
    sched.add(JournalCheckTask())
    sched.add(ArchiveJournalsTask(_archive_journals_queue))
    sched.add(DrugTradeTask(_drug_trade_queue))
    sched.add(IllnessTask(_illness_queue))
    sched.add(GymTask())
    sched.add(CasinoTask())
    sched.add(OnlineAgeTask())
    global _bionics_task
    _bionics_task = BionicsTask()
    sched.add(_bionics_task)
    sched.add(RespectTask())
    sched.add(PlayerRefreshTask())
    sched.add(SyncTask())
    sched.add(CheckTopJobTask())
    sched.add(SnipeTopJobTask())
    sched.add(AutoPromoTask())
    sched.add(JailDutiesTask())
    sched.add(JailActionTask())
    sched.add(JailConsumeTask())

    _transfer_state(old_sched, sched)
    return sched


def _open_log_file() -> object:
    logs_dir = os.path.join(paths.data_dir(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + ".log"
    return open(os.path.join(logs_dir, filename), "w", encoding="utf-8", buffering=1)


def _fetch_bar_threads() -> dict:
    import re as _re
    from bs4 import BeautifulSoup as _BS
    BAR_URL = urls.BASE_URL + "/localcity/bar.asp"
    MAIN_URL = urls.BASE_URL + "/main.asp"
    html = browser.navigate(BAR_URL)
    url = browser.current_url()
    if "local.asp" in url:
        browser.navigate(MAIN_URL)
        return {"error": "Bar is currently torched — try again later."}
    soup = _BS(html, "html.parser")
    threads = []
    for a in soup.select("tr.thread td.topic a[href]"):
        href = a.get("href", "")
        title = a.get_text(strip=True)
        m = _re.search(r't=(\d+)', href)
        if m and title:
            threads.append({"id": m.group(1), "title": title})
    browser.navigate(MAIN_URL)
    return {"threads": threads}


def _fetch_jail_inmates() -> dict:
    from bs4 import BeautifulSoup as _BS
    JAIL_URL = urls.BASE_URL + "/localcity/jail.asp"
    MAIN_URL = urls.BASE_URL + "/main.asp"
    html = browser.navigate(JAIL_URL)
    soup = _BS(html, "html.parser")
    inmates = []
    for a in soup.find_all("a", style=lambda v: v and "color: #FFFFFF" in v):
        name = a.get_text(strip=True)
        if name:
            inmates.append(name)
    browser.navigate(MAIN_URL)
    return {"inmates": inmates}


def _should_payback(target: str, c: dict) -> bool:
    mode = c.get("payback_mode", "nobody")
    if mode == "nobody":
        return False
    if mode == "everyone":
        return True
    import players as _pl
    assignment = _pl.load()["lists"].get("agg_crimes", {}).get(target, "")
    if mode == "whitelist_only":
        return assignment == "whitelist"
    if mode == "not_blacklist":
        return assignment != "blacklist"
    return False


def _run(c: dict):
    global state
    headless = c.get("misc", {}).get("headless", False)
    urls.set_domain("mafiamatrix.net")

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
        browser.start(headless=headless)
        state.add_log("Browser started.")
    except Exception as e:
        state.add_log(f"Browser failed to start: {e}")
        state.last_error = str(e)
        state.bot_running = False
        return

    try:
        global _sched, _state
        sched = _build_scheduler(c)
        _sched = sched
        _state = state

        _startup_earns_done = not c.get("earns", {}).get("enabled", False)
        _was_in_jail = False

        while not _stop_event.is_set():
            if _pause_event.is_set():
                time.sleep(1)
                continue

            # Detect Cloudflare challenge — pause and wait for manual resolution
            if browser.is_cloudflare_challenge():
                msg = (
                    "Cloudflare gateway detected — manual takeover required. "
                    "Complete the challenge in the browser then press Resume."
                )
                state.add_log(msg)
                if c.get("notifications", {}).get("cloudflare_detected", False):
                    state.push_notification("cloudflare_detected", msg)
                _pause_event.set()
                continue

            # Detect session expiry on every tick
            if state.logged_in and browser.current_url().rstrip("/") == urls.BASE_URL + "/default.asp" and not browser.is_cloudflare_challenge():
                state.logged_in = False
                if c.get("misc", {}).get("relog_on_session_expire", True):
                    msg = "Session expired — will re-login."
                    state.add_log(msg)
                    if c.get("notifications", {}).get("session_expired", False):
                        state.push_notification("session_expired", msg)
                else:
                    msg = "Session expired — re-login disabled, pausing."
                    state.add_log(msg)
                    if c.get("notifications", {}).get("session_expired", False):
                        state.push_notification("session_expired", msg)
                    state.relog_suppressed = True
                    _pause_event.set()

            # Bar threads requests from the Flask thread
            if not _bar_threads_request.empty():
                try:
                    _bar_threads_request.get_nowait()
                    _bar_threads_result.put(_fetch_bar_threads())
                except Exception as e:
                    _bar_threads_result.put(e)

            # Jail inmates requests from the Flask thread
            if not _jail_inmates_request.empty():
                try:
                    _jail_inmates_request.get_nowait()
                    _jail_inmates_result.put(_fetch_jail_inmates())
                except Exception as e:
                    _jail_inmates_result.put(e)

            # Warrants check requests from the Flask thread
            if not _warrants_request.empty():
                try:
                    _warrants_request.get_nowait()
                    result_q = queue.Queue()
                    executor.execute(Action("check_warrants", result_queue=result_q), state)
                    _warrants_result.put(result_q.get(timeout=30))
                except Exception as e:
                    _warrants_result.put(e)

            # Turn-in warrant requests
            if not _turn_in_warrant_queue.empty():
                try:
                    params = _turn_in_warrant_queue.get_nowait()
                    executor.execute(Action("turn_in_warrant", **params), state)
                except Exception as e:
                    state.add_log(f"Turn in warrant error: {e}")

            # Travel requests
            if not _travel_queue.empty():
                try:
                    params = _travel_queue.get_nowait()
                    executor.execute(Action("travel", **params), state)
                except Exception as e:
                    state.add_log(f"Travel error: {e}")

            # Travel destination fetch (for UI dropdowns)
            if not _travel_dests_request.empty():
                try:
                    method = _travel_dests_request.get_nowait()
                    _travel_dests_result.put(_fetch_travel_dests(method))
                except Exception as e:
                    _travel_dests_result.put(e)

            if _stop_event.is_set():
                break

            # Reload config and rebuild scheduler if Save was pressed (debounced)
            if _reload_event.is_set() and time.monotonic() - _reload_requested_at >= _RELOAD_DEBOUNCE:
                _reload_event.clear()
                c = cfg.load()
                sched = _build_scheduler(c, old_sched=sched)
                _sched = sched
                state.add_log("Config reloaded.")

            sched.tick(state, executor)
            _scheduler_snapshot = sched.snapshot(state)

            if not _startup_earns_done and state.logged_in:
                earn_cfg = cfg.load().get("earns", {})
                if earn_cfg.get("enabled", False):
                    earn_type = earn_cfg.get("earn_type", "surgeon")
                    try:
                        executor.execute(Action("check_earns", earn_type=earn_type), state)
                    except Exception as _e:
                        state.add_log(f"Startup earns check failed: {_e}")
                _startup_earns_done = True

            # Respect refresh requests from the Flask thread
            if not _respect_refresh_queue.empty():
                try:
                    _respect_refresh_queue.get_nowait()
                    executor.execute(Action("fetch_respect"), state)
                except Exception as e:
                    state.add_log(f"Respect refresh error: {e}")

            # Clear earn queue if requested from UI
            if _clear_earn_event.is_set():
                _clear_earn_event.clear()
                executor.execute(Action("clear_earn_queue"), state)

            # Clear jail duty queue if requested from UI
            if _clear_jail_duty_queue_event.is_set():
                _clear_jail_duty_queue_event.clear()
                executor.execute(Action("clear_jail_duty_queue"), state)

            # Jailed notification — fires once when in_jail flips True
            if state.in_jail and not _was_in_jail:
                if c.get("notifications", {}).get("jailed", False):
                    state.push_notification("jailed", "Bot went to jail.")
            _was_in_jail = state.in_jail

            # Payback after a successful crime
            if getattr(state, "_last_crime_victim", None):
                victim = state._last_crime_victim
                amount = state._last_crime_amount
                del state._last_crime_victim
                del state._last_crime_amount
                if _should_payback(victim, c):
                    executor.execute(Action("payback", amount=amount, target=victim), state)

            time.sleep(2)

    except Exception as e:
        state.add_log(f"Bot crashed: {e}")
    finally:
        try:
            if state.logged_in and c.get("misc", {}).get("logout_on_stop", True):
                state.add_log("Logging out...")
                browser.navigate(urls.BASE_URL + "/default.asp?action=logout")
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


def get_bionics_task():
    return _bionics_task


def get_state():
    return _state


def get_scheduler_snapshot() -> list:
    if _sched is not None and _state is not None:
        try:
            return _sched.snapshot(_state)
        except Exception:
            pass
    return _scheduler_snapshot


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


def request_deposit():
    _deposit_queue.put(True)


def request_withdraw(amount: int):
    _withdraw_queue.put(amount)


def request_char_history_refresh():
    _char_history_queue.put(True)


def request_jailbreak_plan(target: str, partner: str, hold_action_timer: bool):
    if hold_action_timer and _state is not None:
        _state.hold_action_timer = True
    _jailbreak_plan_queue.put({
        "target": target,
        "partner": partner,
        "hold_action_timer": hold_action_timer,
    })


def request_jailbreak_execute():
    _jailbreak_execute_queue.put(True)


def request_jailbreak_calloff():
    _jailbreak_calloff_queue.put(True)


def request_archive_journals(pages: int | None = None):
    _archive_journals_queue.put({"pages": pages})


def request_jail_inmates(timeout: float = 15.0) -> dict:
    while not _jail_inmates_result.empty():
        _jail_inmates_result.get_nowait()
    _jail_inmates_request.put(True)
    result = _jail_inmates_result.get(timeout=timeout)
    if isinstance(result, Exception):
        raise result
    return result


def online_population() -> dict:
    """Parse whosonlinecell from current page HTML — no navigation needed."""
    import re as _re
    from bs4 import BeautifulSoup as _BS
    import players as _pl
    html = state.page_html
    own = state.own_name
    is_gangster = (state.occupation or "").lower() == "gangster"
    own_city = (state.home_city or "").lower()
    soup = _BS(html, "html.parser")
    cell = soup.find("div", id="whosonlinecell")
    jail_inmates = []
    partners = []
    _GANGSTER_CLASSES = {"crime", "crewleader", "godfather"}
    _EXCLUDE_CLASSES = {"crime", "crewleader", "godfather", "cdtc", "jail"}
    player_store = _pl.load().get("players", {})
    if cell:
        for a in cell.find_all("a", id=_re.compile(r"^profileLink:")):
            parts = a.get("id", "").split(":")
            if len(parts) < 2:
                continue
            name = parts[1]
            classes = set(a.get("class", []))
            if "jail" in classes:
                jail_inmates.append(name)
            if "normal" in classes and name != own:
                if is_gangster:
                    if classes & _GANGSTER_CLASSES:
                        partners.append(name)
                else:
                    if not (classes & _EXCLUDE_CLASSES):
                        p = player_store.get(name, {})
                        p_city = p.get("homecity", "").lower()
                        if p_city == own_city:
                            partners.append(name)
    return {
        "jail_inmates": sorted(jail_inmates),
        "partners": sorted(partners),
    }


def request_respect_refresh():
    _respect_refresh_queue.put(True)


def request_clear_earn_queue():
    _clear_earn_event.set()


def request_clear_jail_duty_queue():
    _clear_jail_duty_queue_event.set()


def request_bar_threads(timeout: float = 15.0) -> dict:
    while not _bar_threads_result.empty():
        _bar_threads_result.get_nowait()
    _bar_threads_request.put(True)
    result = _bar_threads_result.get(timeout=timeout)
    if isinstance(result, Exception):
        raise result
    return result



def request_warrants(timeout: float = 30.0) -> list:
    while not _warrants_result.empty():
        _warrants_result.get_nowait()
    _warrants_request.put(True)
    result = _warrants_result.get(timeout=timeout)
    if isinstance(result, Exception):
        raise result
    return result


def request_turn_in_warrant(url: str, case_id: str):
    _turn_in_warrant_queue.put({"url": url, "case_id": case_id})


def request_travel(target_city: str, method: str):
    _travel_queue.put({"target_city": target_city, "method": method})


def _fetch_travel_dests(method: str) -> list:
    from bs4 import BeautifulSoup as _BS
    import urls as _urls
    if method == "own_vehicle":
        html = browser.navigate(_urls.BASE_URL + "/travel/travel.asp")
        soup = _BS(html, "html.parser")
        sel = soup.find("select", attrs={"name": "vehicletravel"})
        if not sel:
            return []
        return [
            {"value": o["value"], "label": o.get_text(strip=True)}
            for o in sel.find_all("option") if o.get("value")
        ]
    else:
        html = browser.navigate(_urls.BASE_URL + "/travel/airport.asp")
        soup = _BS(html, "html.parser")
        sel = soup.find("select", attrs={"name": "destination"})
        if not sel:
            return []
        return [
            {
                "value": o["value"],
                "label": o.get_text(strip=True),
                "costs": o.get("data-costs", ""),
                "minutes": o.get("data-minutes", ""),
            }
            for o in sel.find_all("option")
            if o.get("value") and o.get("value") != "0"
        ]


def request_travel_dests(method: str, timeout: float = 15.0) -> list:
    while not _travel_dests_result.empty():
        _travel_dests_result.get_nowait()
    _travel_dests_request.put(method)
    result = _travel_dests_result.get(timeout=timeout)
    if isinstance(result, Exception):
        raise result
    return result
