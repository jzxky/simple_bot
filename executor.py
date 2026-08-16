"""
ActionExecutor: maps Action.kind to handler functions that drive the browser.
"""

import json
import queue
import random
import re
import time
import config as cfg
import urls
from bs4 import BeautifulSoup
from tasks.base import Action
from state import GameState, parse_state
import browser


# Cooldown set when pre-travel warrant check finds unresolvable warrants.
_travel_warrant_cooldown_until: float = 0.0


def travel_warrant_cooldown_active() -> bool:
    """True while the post-warrant travel cooldown is in effect. Auto-travel tasks
    (casino, gym) check this so they don't re-attempt travel every cycle while
    outstanding warrants block it."""
    return time.monotonic() < _travel_warrant_cooldown_until


# Cooldown set when drug manufacturing returns a fail div.
_drug_manufacture_cooldown_until: float = 0.0


def drug_manufacture_cooldown_active() -> bool:
    """True while the drug-manufacturing fail cooldown is in effect."""
    return time.monotonic() < _drug_manufacture_cooldown_until


_gym_travel_cooldown_until: float = 0.0


def gym_travel_cooldown_active() -> bool:
    return time.monotonic() < _gym_travel_cooldown_until


_launder_cooldown_until: float = 0.0
_launder_cooldown_city: str = ""


def launder_cooldown_active(current_city: str = "") -> bool:
    if time.monotonic() >= _launder_cooldown_until:
        return False
    if current_city and _launder_cooldown_city and current_city != _launder_cooldown_city:
        return False
    return True


def clear_launder_cooldown():
    global _launder_cooldown_until, _launder_cooldown_city
    _launder_cooldown_until = 0.0
    _launder_cooldown_city = ""


def launder_cooldown_remaining() -> int:
    return max(0, int(_launder_cooldown_until - time.monotonic()))


def _u(path: str) -> str:
    return urls.BASE_URL + path


def _notify(state: GameState, event_type: str, message: str):
    if cfg.load().get("notifications", {}).get(event_type, False):
        state.push_notification(event_type, message)


def _window_start_offset(prev_ingame, cur_ingame) -> int:
    """In-game minutes to add to the current game time for an auto-detected
    restock window's *start*.

    The restock happened at some point between the previous store check and now.
    Anchoring to the earliest possible restock (the previous check) opens the
    window sooner so a restock isn't missed:
    Start = 10.5h - min(time-since-last-check, 0.5h).
    When the previous in-game time is unknown, assume the full 0.5h cap.
    (The window end stays at current time + 13.5h.)
    """
    cap = 30  # 0.5 hours, in game minutes
    if prev_ingame is None or cur_ingame is None:
        tslc = cap
    else:
        tslc = (int(cur_ingame) - int(prev_ingame)) % (24 * 60)
    return 10 * 60 + 30 - min(tslc, cap)

_DRUG_TRADE_NAME_MAP = {
    "marijuana": "marijuana",
    "cocaine":   "cocaine",
    "ecstasy":   "ecstasy",
    "acid":      "acid",
    "speed":     "speed",
    "p/ice":     "pice",
    "p / ice":   "pice",
    "pice":      "pice",
    "heroin":    "heroin",
}

JAIL_CONSUMABLE_NAMES = {
    "cigarettes": "Cigarettes",
    "booze":      "Booze",
    "porn":       "Porn",
    "heroin":     "Heroin",
    "shanks":     "Shanks",
}

# Maps state key → actual radio button value on contraband.asp
_JAIL_RADIO_VALUE = {
    "porn":       "porn",
    "booze":      "drink",
    "cigarettes": "cigarettes",
    "heroin":     "chasing",
}

ONLINE_CRIMES = {"pickpocket", "mugging"}
RESIDENT_CRIMES = {"hack", "breaking"}

# Typeahead writable input (not the readonly tt-hint shadow field)
_TARGET_INPUT = "input.tt-input, input[type='text']:not(.tt-hint)"

QUEUE_MIN = 50
QUEUE_MAX = 200

MUGGING_WEAPONS = {"Baseball Bat", "Pistol"}
BODY_PARTS = {"Arms", "Legs", "Eyes", "Brain", "Heart"}

PUBLIC_BUSINESSES = {
    "Funeral Parlour", "Town Hall", "Hospital", "Fire Station",
    "Airport", "Construction Company", "Bank Tills"
}

PUBLIC_JOB_MAP = {
    "Funeral Parlour": "Funeral Director",
    "Town Hall": "Mayor",
    "Hospital": "Hospital Director",
    "Fire Station": "Fire Chief",
    "Airport": "Commissioner-General",
    "Construction Company": "Chief Engineer",
    "Bank Tills": "Bank Manager",
    "Bank": "Bank Manager",
}

TORCH_PUBLIC_BUSINESSES = {
    "Funeral Parlour", "Bank", "Airport", "Construction Company", "Town Hall", "Hospital"
}

ARMED_MAX_RETRIES = 6


def _match_public_business(name: str, public_set) -> "str | None":
    """Return the canonical public-business type if `name` matches it exactly or
    as a city-prefixed variant (e.g. 'Auckland Bank Tills' → 'Bank Tills'); else None.
    The leading-space check keeps the match to a city prefix, avoiding loose
    substring false positives on private business names."""
    for pub in public_set:
        if name == pub or name.endswith(" " + pub):
            return pub
    return None


def _refresh_state(state: GameState):
    html = browser.page().content()
    url = browser.current_url()
    parse_state(html, url, state)


def _dbg(state: GameState, msg: str):
    import config as _cfg
    if _cfg.load().get("misc", {}).get("debug_logging", False):
        state.add_log(f"[DEBUG] {msg}")


def _nav(url: str, state: GameState):
    _dbg(state, f"→ {url}")
    html = browser.navigate(url)
    parse_state(html, browser.current_url(), state)


def _check_session(state: GameState) -> bool:
    """Return True if still logged in, False if redirected to login page."""
    if browser.current_url().rstrip("/") == _u("/default.asp"):
        state.logged_in = False
        state.add_log("Session expired, will re-login.")
        return False
    return True


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_login(action: Action, state: GameState):
    page = browser.page()

    # If already on the game, mark logged in and return
    if "default.asp" not in browser.current_url() and browser.current_url() != "about:blank":
        state.logged_in = True
        return

    page.goto(_u("/default.asp"), wait_until="load")

    try:
        page.wait_for_selector("form#loginForm", timeout=10000)
    except Exception:
        state.add_log("Login form not found — retrying in 10s.")
        time.sleep(10)
        return

    page.fill("input#email", action.params["email"])
    page.fill("input#pass", action.params["password"])
    page.click("button.btn-login")
    page.wait_for_load_state("networkidle")

    _refresh_state(state)
    soup = BeautifulSoup(page.content(), "html.parser")

    err = soup.find("div", class_="info red")
    if err and "Login failed" in err.get_text():
        state.logged_in = False
        state.last_error = "Login failed: incorrect credentials."
        state.add_log(state.last_error)
        state.bot_running = False
        return

    # Click PLAY NOW if present
    play = soup.find("a", class_="btn-play")
    if play:
        page.goto(_u("/loggedin.asp?display=play"), wait_until="load")
        _refresh_state(state)

    state.logged_in = True
    state.add_log("Logged in successfully.")


def _scrape_earn_catalog(page, state: GameState):
    """Navigate to earn.asp, scrape available options, update catalog. Returns (auto_opts, available_values)."""
    _nav(_u("/income/earn.asp"), state)
    if not _check_session(state):
        return [], []

    # Wait for the earn page body to be present before querying
    try:
        page.wait_for_selector("#content", timeout=10000)
    except Exception:
        pass

    auto_div = page.query_selector("div.mm-earn-mode-auto")
    if auto_div:
        style = auto_div.get_attribute("style") or ""
        if "display: none" in style or "display:none" in style:
            page.click("span.mm-earn-toggle-knob")
            page.wait_for_function(
                "() => { const el = document.querySelector('div.mm-earn-mode-auto'); "
                "return el && !el.style.display.includes('none'); }",
                timeout=5000
            )
            page.wait_for_selector(
                "select[name='schedule_earn_identifier']",
                state="visible", timeout=5000,
            )
            state.add_log("Switched to AUTO earn mode.")

    soup = BeautifulSoup(page.content(), "html.parser")
    auto_panel = soup.find("div", class_="mm-earn-mode-auto")
    available_values = []
    auto_opts = []
    if auto_panel:
        sel = auto_panel.find("select", attrs={"name": "schedule_earn_identifier"})
        if sel:
            for o in sel.find_all("option"):
                if o.get("value"):
                    available_values.append(o.get("value", ""))
                    auto_opts.append((o.get("value", ""), o.get_text(strip=True)))

    manual_opts = []
    manual_div = soup.find("div", id="earns_list")
    if manual_div:
        for wrapper in manual_div.find_all("div", class_="earn-option"):
            data_earn = wrapper.get("data-earn", "")
            span = wrapper.find("span")
            if not span:
                continue
            is_trap = bool(span.find("s"))
            label = span.get_text(strip=True)
            manual_opts.append((data_earn, label, is_trap))

    if auto_opts or manual_opts:
        try:
            _upsert_earn_catalog(auto_opts, manual_opts)
        except Exception:
            pass
        auto_labels = ", ".join(f"{v} ({l})" for v, l in auto_opts) or "none"
        manual_labels = ", ".join(f"{d}:{l}" + (" [trap]" if t else "") for d, l, t in manual_opts) or "none"
        if cfg.load().get("debug_logging", False):
            state.add_log(f"Earns detected — auto: [{auto_labels}] | manual: [{manual_labels}]")
    else:
        state.add_log("Earns: no options detected on earn page.")

    return auto_opts, available_values


def _parse_earn_queue_rows(soup) -> list:
    """Parse the earn queue list into (name, completed, total) tuples.
    Each .mm-earn-queue-row has a name and a 'completed/total' count cell."""
    rows = []
    for row in soup.find_all("div", class_="mm-earn-queue-row"):
        name_el = row.find("div", class_="mm-earn-queue-row-name")
        count_el = row.find("div", class_="mm-earn-queue-row-count")
        if not name_el or not count_el:
            continue
        name = name_el.get_text(strip=True)
        txt = count_el.get_text(strip=True)
        if "/" not in txt:
            continue
        done_s, _, total_s = txt.partition("/")
        try:
            done = int(done_s.strip())
            total = int(total_s.strip())
        except ValueError:
            continue
        rows.append((name, done, total))
    return rows


def _ensure_auto_earn_mode(page):
    """Make sure the AUTO earn panel is visible (it can collapse after a page reload)."""
    try:
        page.wait_for_selector("div.mm-earn-mode-auto", timeout=5000)
    except Exception:
        return
    auto_div = page.query_selector("div.mm-earn-mode-auto")
    if not auto_div:
        return
    style = auto_div.get_attribute("style") or ""
    if "display: none" in style or "display:none" in style:
        page.click("span.mm-earn-toggle-knob")
        page.wait_for_function(
            "() => { const el = document.querySelector('div.mm-earn-mode-auto'); "
            "return el && !el.style.display.includes('none'); }",
            timeout=5000,
        )
    page.wait_for_selector(
        "select[name='schedule_earn_identifier']",
        state="visible", timeout=5000,
    )


def _queue_earn(page, value: str, amount: int, state: GameState) -> bool:
    """Add `amount` of one auto-earn to the queue. Returns True on success."""
    try:
        _ensure_auto_earn_mode(page)
        page.select_option("select[name='schedule_earn_identifier']", value)
        page.fill("input[name='schedule_count']", str(amount))
        page.click("button.mm-earn-add-btn")
        page.wait_for_load_state("domcontentloaded")
        state.add_log(f"Earn queue: added {amount} x {value}.")
        return True
    except Exception as e:
        state.add_log(f"Earn queue: failed to add {value} ({e}).")
        return False


def handle_refresh_earn_catalog(action: Action, state: GameState):
    """Scrape the earn page and update available_earns.json — no queue action."""
    _scrape_earn_catalog(browser.page(), state)


def handle_check_earns(action: Action, state: GameState):
    earn_type = action.params["earn_type"]
    page = browser.page()

    # Fetch character history first — it navigates away from earn.asp.
    import earn_planner as _ep
    import character_history as _ch
    try:
        _ch.fetch_and_save(state.own_name or "")
    except Exception:
        pass

    auto_opts, available_values = _scrape_earn_catalog(page, state)
    if not available_values:
        return

    if earn_type not in available_values:
        state.add_log(f"Earn '{earn_type}' is not available — disabling earns. Select a new earn and save to re-enable.")
        c = cfg.load()
        c["earns"]["enabled"] = False
        cfg.save(c)
        return

    # Read queue count from current page content
    earn_soup = BeautifulSoup(page.content(), "html.parser")
    cap_span = earn_soup.find("span", class_="mm-earn-queue-cap")
    current_count = 0
    if cap_span:
        try:
            current_count = int(cap_span.get_text(strip=True).split("/")[0].strip())
        except (ValueError, IndexError):
            pass

    if current_count >= QUEUE_MIN:
        state.add_log(f"Earn queue at {current_count}/200, no top-up needed.")
        return

    available_capacity = QUEUE_MAX - current_count

    queue_rows = _parse_earn_queue_rows(earn_soup)
    limits = cfg.load().get("earn_planner", {}).get("limits", {})

    # Queue order: the active earn first, then any other planner earns (those with
    # limits), all restricted to currently auto-earnable values.
    candidates = [earn_type] + [v for v in limits if v != earn_type]
    candidates = [v for v in candidates if v in available_values]

    new_active = None
    for value in candidates:
        if available_capacity <= 0:
            break
        limit = limits.get(value)
        if limit:
            # Progress toward the lifetime cap = completed (history) + already queued.
            completed = _ep.completed_count(value)
            queued = _ep.queued_remaining(value, queue_rows)
            need = int(limit) - completed - queued
            if need <= 0:
                if value == earn_type:
                    state.add_log(
                        f"Earn planner: '{value}' at cap "
                        f"({completed} done + {queued} queued ≥ {limit}) — moving to next earn."
                    )
                continue
            amount = min(need, available_capacity)
        else:
            # No cap configured for this earn — fill the remaining capacity.
            amount = available_capacity

        if amount <= 0:
            continue
        if not _queue_earn(page, value, amount, state):
            continue
        available_capacity -= amount
        if new_active is None:
            new_active = value

    if new_active is None:
        state.add_log("Earn planner: nothing to queue (all listed earns at cap or no capacity).")
        return

    _refresh_state(state)

    # Reflect a planner-driven earn switch in config so the UI updates.
    if new_active != earn_type:
        c = cfg.load()
        c["earns"]["earn_type"] = new_active
        cfg.save(c)
        state.add_log(f"Earn planner: active earn updated to {new_active}.")


def handle_clear_earn_queue(action: Action, state: GameState):
    page = browser.page()
    _nav(_u("/income/earn.asp"), state)

    if not _check_session(state):
        return

    # Ensure AUTO panel is visible
    _ensure_auto_earn_mode(page)

    btn = page.query_selector("button.mm-earn-queue-clear-btn")
    if not btn:
        state.add_log("Clear queue button not found on earn page.")
        return

    btn.click()
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log("Earn queue cleared.")

    c = cfg.load()
    if c.get("earns", {}).get("enabled", False):
        earn_type = c["earns"].get("earn_type", "surgeon")
        handle_check_earns(Action("check_earns", earn_type=earn_type), state)


def _load_earn_catalog():
    import paths, os, json as _json
    path = os.path.join(paths.data_dir(), "available_earns.json")
    if not os.path.exists(path):
        return list(_EARN_SEED)
    try:
        with open(path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return list(_EARN_SEED)


def _earn_display_name(schedule_value: str) -> str:
    for entry in _load_earn_catalog():
        if entry.get("schedule_value") == schedule_value:
            return entry["label"]
    import earn_planner as _ep
    return _ep.HISTORY_NAME.get(schedule_value, schedule_value)


def _earn_data_earn(schedule_value: str):
    for entry in _load_earn_catalog():
        if entry.get("schedule_value") == schedule_value:
            return entry.get("data_earn")
    return None


def _try_quick_earn(page, display_name: str, schedule_value: str, state: GameState) -> bool:
    links = page.query_selector_all("a[href*='doLoadfastincome']")
    for link in links:
        href = link.get_attribute("href") or ""
        match = re.search(r"doLoadfastincome\('([^']+)'", href)
        if not match:
            continue
        lastearn_text = match.group(1)
        catalog = _load_earn_catalog()
        matched = False
        if lastearn_text.lower() == display_name.lower():
            matched = True
        else:
            for entry in catalog:
                if entry.get("schedule_value") == schedule_value:
                    if entry.get("lastearn_name", "").lower() == lastearn_text.lower():
                        matched = True
                    break
        if not matched:
            continue
        link.click()
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        try:
            page.wait_for_selector("input[name='lastearn']", timeout=5000)
        except Exception:
            pass
        lastearn = page.query_selector("input[name='lastearn']")
        if lastearn:
            lastearn.click()
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
            except Exception:
                pass
            state.add_log(f"Manual earn: quick-earn '{display_name}' — submitted via lastearn.")
            _map_lastearn_to_catalog(lastearn_text, schedule_value)
        else:
            state.add_log(f"Manual earn: quick-earn '{display_name}' — lastearn input not found.")
        _refresh_state(state)
        return True
    return False


def _ensure_manual_earn_mode(page, state: GameState):
    manual_div = page.query_selector("div.mm-earn-mode-manual")
    if not manual_div:
        return
    style = manual_div.get_attribute("style") or ""
    if "display: none" not in style and "display:none" not in style:
        return
    btn = page.query_selector("button.mm-earn-queue-clear-btn")
    if btn:
        btn.click()
        page.wait_for_load_state("domcontentloaded")
        state.add_log("Earn queue cleared before switching to manual.")
    page.click("span.mm-earn-toggle-knob")
    page.wait_for_function(
        "() => { const el = document.querySelector('div.mm-earn-mode-manual'); "
        "return el && !el.style.display.includes('none'); }",
        timeout=5000
    )
    state.add_log("Switched to MANUAL earn mode.")


def _map_lastearn_to_catalog(lastearn_text: str, schedule_value: str):
    """Update the earn catalog so the lastearn display name maps to the schedule_value."""
    import paths, os, json as _json
    path = os.path.join(paths.data_dir(), "available_earns.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            entries = _json.load(f)
    except Exception:
        return
    for entry in entries:
        if entry.get("schedule_value") == schedule_value:
            if entry.get("lastearn_name") != lastearn_text:
                entry["lastearn_name"] = lastearn_text
                with open(path, "w", encoding="utf-8") as f:
                    _json.dump(entries, f, indent=2)
            return


def handle_manual_earn(action: Action, state: GameState):
    earn_type = action.params["earn_type"]
    page = browser.page()
    display_name = _earn_display_name(earn_type)

    if _try_quick_earn(page, display_name, earn_type, state):
        return

    _nav(_u("/income/earn.asp"), state)
    if not _check_session(state):
        return

    _scrape_earn_catalog(page, state)
    _ensure_manual_earn_mode(page, state)

    data_earn = _earn_data_earn(earn_type)
    option = None
    if data_earn is not None:
        option = page.query_selector(f"div.earn-option[data-earn='{data_earn}']")

    if not option:
        options = page.query_selector_all("div.earn-option")
        for opt in options:
            span = opt.query_selector("span")
            if span and span.inner_text().strip().lower() == display_name.lower():
                option = opt
                break

    if not option:
        state.add_log(f"Manual earn: could not find '{display_name}' in earn list.")
        return

    trapped = option.query_selector("s")
    if trapped:
        state.add_log(f"Manual earn: '{display_name}' is trapped (red) — skipping.")
        return

    option.click()
    time.sleep(0.3)

    work_btn = page.query_selector("button.btn-new.bg-mm")
    if not work_btn:
        state.add_log("Manual earn: Work button not found.")
        return

    work_btn.click()
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log(f"Manual earn: worked '{display_name}'.")

    for lnk in page.query_selector_all("a[href*='doLoadfastincome']"):
        href = lnk.get_attribute("href") or ""
        m = re.search(r"doLoadfastincome\('([^']+)'", href)
        if m:
            _map_lastearn_to_catalog(m.group(1), earn_type)
            break


def _get_online_local_players(state: GameState) -> list:
    """Parse the who's online sidebar from the current page HTML."""
    soup = BeautifulSoup(state.page_html, "html.parser")
    cell = soup.find("div", id="whosonlinecell")
    if not cell:
        return []
    players = []
    for a in cell.find_all("a"):
        aid = a.get("id", "")
        parts = aid.split(":")
        if len(parts) < 3:
            continue
        name, status = parts[1], parts[2]
        if status == "In-Jail" or name == state.own_name:
            continue
        if "Angel" in parts:
            continue
        players.append(name)
    return players


def _get_city_residents(city: str, own_name: str) -> list:
    """Fetch all players whose home city matches, via updateusers.php."""
    browser.page().goto(_u("/skin/updateusers.php?q=1"), wait_until="domcontentloaded", timeout=15000)
    text = browser.page().inner_text("body")
    try:
        data = json.loads(text)
    except Exception:
        return []
    return [
        p["userName"] for p in data
        if p.get("userHomeCity") == city and p.get("userName") != own_name
    ]


_LAUNDER_EXCLUDE_CITIES = {"Heaven", "Hell", "Manila", "Locked"}


def handle_bulk_add_launder_contacts(action: Action, state: GameState):
    """Establish a money-laundering deal with every eligible player.

    Eligible = not in an excluded city/state, not in the bot's own home city,
    not Unemployed, and not the bot itself."""
    page = browser.page()

    if not state.in_home_city():
        state.add_log("Bulk launder: not in home city — aborting.")
        return

    try:
        page.goto(_u("/skin/updateusers.php?q=1"), wait_until="domcontentloaded", timeout=15000)
        data = json.loads(page.inner_text("body"))
    except Exception as e:
        state.add_log(f"Bulk launder: failed to load user list ({e}).")
        return

    names = [
        p["userName"] for p in data
        if p.get("userHomeCity") not in _LAUNDER_EXCLUDE_CITIES
        and p.get("userHomeCity") != state.home_city
        and p.get("userOccupation") != "Unemployed"
        and p.get("userName") != state.own_name
    ]
    if not names:
        state.add_log("Bulk launder: no eligible candidates found.")
        return

    state.add_log(f"Bulk launder: establishing deals with {len(names)} contact(s).")

    _ESTABLISH_URL = _u("/income/banklaunder.asp?display=establish")

    def _ensure_form() -> bool:
        """Mirror the crime loop: only navigate to the establish page when the
        gangster input isn't already on the current page."""
        if page.query_selector("input[name='gangster']"):
            return True
        page.goto(_ESTABLISH_URL, wait_until="domcontentloaded", timeout=15000)
        return bool(page.query_selector("input[name='gangster']"))

    if not _ensure_form() or not _check_session(state):
        state.add_log("Bulk launder: establish form not available — aborting.")
        return

    established = 0
    failed = 0
    for name in names:
        try:
            if not _ensure_form():
                state.add_log("Bulk launder: lost establish form mid-run — aborting.")
                break
            page.fill("input[name='gangster']", name)
            page.click("input[name='B1']")
            page.wait_for_load_state("domcontentloaded")

            soup = BeautifulSoup(page.content(), "html.parser")
            fail_div = soup.find("div", id="fail")
            success_div = soup.find("div", id="success")
            if fail_div:
                failed += 1
                state.add_log(f"Bulk launder {name}: {fail_div.get_text(strip=True)}")
            elif success_div:
                established += 1
                state.add_log(f"Bulk launder {name}: {success_div.get_text(strip=True)}")
            else:
                state.add_log(f"Bulk launder {name}: submitted (no result div).")
        except Exception as e:
            failed += 1
            state.add_log(f"Bulk launder {name}: error ({e}).")

    _refresh_state(state)
    state.add_log(f"Bulk launder: done ({established} established, {failed} failed).")


def _parse_money(text: str) -> int:
    """Parse '$31,250' / '$0' → int."""
    digits = re.sub(r"[^0-9]", "", text or "")
    return int(digits) if digits else 0


def _count_launder_queue(state: GameState):
    """Navigate to banklaunder.asp, count pending deals, save to config. Returns list of (name, url)."""
    page = browser.page()
    _nav(_u("/income/banklaunder.asp"), state)
    if not _check_session(state):
        return []

    soup = BeautifulSoup(page.content(), "html.parser")
    table = soup.find("table", style=lambda s: s and "90%" in s)
    if not table:
        _save_launder_queue_size(0)
        return []

    pending = []
    for row in table.find_all("tr"):
        cells = row.find_all("td", class_="display_border")
        if len(cells) < 3:
            continue
        name = cells[0].get_text(strip=True)
        balance = _parse_money(cells[2].get_text(strip=True))
        if balance <= 5:
            continue
        link = cells[2].find("a", href=True)
        if not link:
            continue
        href = link["href"]
        url = _u("/income/") + href if not href.startswith("http") else href
        pending.append((name, url))

    _save_launder_queue_size(len(pending))
    return pending


def _save_launder_queue_size(size: int):
    import config as _cfg
    c = _cfg.load()
    c.setdefault("banking", {})["launder_queue_size"] = size
    _cfg.save(c)


def _do_one_launder(pending, state: GameState) -> bool:
    """Attempt to launder the first pending deal. Returns True if successful."""
    page = browser.page()
    for name, url in pending:
        try:
            _nav(url, state)
            sel = page.query_selector("select[name='display']")
            if not sel:
                state.add_log(f"Banking {name}: launder form not found — skipping.")
                continue
            page.select_option("select[name='display']", "result")
            page.click("input[type='submit'][name='B1']")
            page.wait_for_load_state("domcontentloaded")

            transfer_btn = page.query_selector("input[name='B1'][value='Auto Funds Transfer']")
            if not transfer_btn:
                soup2 = BeautifulSoup(page.content(), "html.parser")
                fail = soup2.find("div", id="fail")
                msg = fail.get_text(strip=True) if fail else "no transfer form"
                state.add_log(f"Banking {name}: launder produced no transfer ({msg}).")
                return False
            transfer_btn.click()
            page.wait_for_load_state("domcontentloaded")

            soup3 = BeautifulSoup(page.content(), "html.parser")
            success = soup3.find("div", id="success")
            fail = soup3.find("div", id="fail")
            if success:
                state.add_log(f"Banking {name}: {success.get_text(strip=True)}")
                return True
            elif fail:
                state.add_log(f"Banking {name}: transfer failed — {fail.get_text(strip=True)}")
            else:
                state.add_log(f"Banking {name}: transfer submitted (no result div).")
            return False
        except Exception as e:
            state.add_log(f"Banking {name}: error ({e}).")
            return False
    return False


def handle_check_banking_cases(action: Action, state: GameState):
    """Poll the bank-launder deals list; launder one deal, then auto-weed loop if enabled."""
    import config as _cfg

    pending = _count_launder_queue(state)
    if not pending:
        return

    state.add_log(f"Banking: {len(pending)} deal(s) with money to launder.")
    laundered = 0

    if _do_one_launder(pending, state):
        laundered += 1

    # Auto-weed loop: consume marijuana and repeat while conditions are met
    c = _cfg.load()
    banking = c.get("banking", {})
    auto_weed = banking.get("auto_weed", False)
    threshold = int(banking.get("weed_queue_threshold", 5))

    if auto_weed and laundered:
        cons_cfg = c.get("consumables", {})
        cons_limit = int(cons_cfg.get("consumable_limit", 33))
        buffer_ = int(cons_cfg.get("buffer", 0))

        while True:
            pending = _count_launder_queue(state)
            queue_size = len(pending)
            used_24h = state.consumables_24h or 0
            headroom = (cons_limit - buffer_) - used_24h

            if queue_size < threshold:
                state.add_log(f"Auto-weed: queue {queue_size} < threshold {threshold}, stopping.")
                break
            effective_limit = cons_limit - buffer_
            if headroom <= 0:
                state.add_log(f"Auto-weed: daily limit reached ({used_24h}/{effective_limit}), stopping.")
                break
            if not pending:
                break

            # Consume 1x marijuana
            consume_action = Action(kind="consume", type="marijuana", count=1)
            handle_consume(consume_action, state)
            state.add_log(f"Auto-weed: queue {queue_size}/{threshold}, consumed marijuana ({used_24h + 1}/{effective_limit} daily)")

            # Navigate back and launder
            pending = _count_launder_queue(state)
            if not pending:
                state.add_log("Auto-weed: no deals remaining after consume.")
                break
            if _do_one_launder(pending, state):
                laundered += 1
            else:
                break

    _refresh_state(state)
    state.add_log(f"Banking: laundered {laundered} deal(s).")


def _check_cs_punishment(state: GameState) -> bool:
    """
    Call after navigating to agcrime.asp when no target input is found.
    If the page is income.asp with a CS-punishment fail message, parse the
    sentence count, store it in state, and return True.
    """
    url = browser.current_url()
    if "/income/income.asp" not in url and "/income/agcrime.asp" not in url:
        return False
    soup = BeautifulSoup(browser.page().content(), "html.parser")
    fail_div = soup.find("div", id="fail")
    if not fail_div:
        return False
    text = fail_div.get_text(strip=True)
    # Message: "You cannot commit an aggravated crime until you have completed another N Services..."
    m = re.search(r"complete(?:d)? another (\d+) Services?", text, re.IGNORECASE)
    if not m:
        return False
    n = int(m.group(1))
    state.cs_sentence = n
    state.add_log(f"Agg crime blocked: CS punishment — must complete {n} community service(s).")
    return True


def _nav_to_target_input(crime: str, state: GameState) -> bool:
    """Navigate to agcrime.asp, select crime, submit — returns True if text input found."""
    page = browser.page()
    _nav(_u("/income/agcrime.asp"), state)
    if not page.query_selector(f"input[name='agcrime'][value='{crime}']"):
        msg = f"Agg crime '{crime}' not on the available list — disabling."
        state.add_log(msg)
        c = cfg.load()
        c.setdefault("aggravated_crimes", {})["enabled"] = False
        cfg.save(c)
        if c.get("notifications", {}).get("agg_not_available", False):
            state.push_notification("agg_not_available", msg)
        return False
    page.check(f"input[name='agcrime'][value='{crime}']")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    return bool(page.query_selector(_TARGET_INPUT))


def _back_to_target_input(crime: str, state: GameState) -> bool:
    """Go back one step; fall back to full navigation if text input isn't there."""
    page = browser.page()
    page.go_back(wait_until="domcontentloaded")
    if page.query_selector(_TARGET_INPUT):
        return True
    return _nav_to_target_input(crime, state)


_MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1"
)


def handle_breaking_entering(action: Action, state: GameState):
    """Breaking & Entering — uses mobile UA so the dropdown form is served."""
    threshold = action.params.get("threshold", 0)
    page = browser.page()

    page.set_extra_http_headers({"User-Agent": _MOBILE_UA})
    try:
        _nav(_u("/income/agcrime.asp"), state)
        if not _check_session(state):
            return

        page.check("input[name='agcrime'][value='breaking']")
        page.click("input[type='submit'][name='B1']")
        page.wait_for_load_state("domcontentloaded")

        soup = BeautifulSoup(page.content(), "html.parser")
        select = soup.find("select", {"name": "breaking", "class": "dropdown"})
        if not select:
            if not _check_cs_punishment(state):
                state.add_log("Breaking & Entering: dropdown not found after crime selection.")
            return

        options = [o["value"] for o in select.find_all("option") if o.get("value")]
        if not options:
            state.add_log("Breaking & Entering: no targets in dropdown.")
            return

        state.add_log(f"Breaking & Entering: {len(options)} targets found.")

        fail_counts: dict = {}

        def _flush_fails():
            if not fail_counts:
                return
            total = sum(fail_counts.values())
            parts = ", ".join(f"{n}x {msg}" for msg, n in fail_counts.items())
            state.add_log(f"B&E run: {total} fail{'s' if total != 1 else ''} — {parts} (fail count: {state.agg_fail_count()}/3)")
            fail_counts.clear()

        def _ensure_dropdown() -> bool:
            if page.query_selector("select[name='breaking']"):
                return True
            _nav(_u("/income/agcrime.asp"), state)
            if not _check_session(state):
                return False
            page.check("input[name='agcrime'][value='breaking']")
            page.click("input[type='submit'][name='B1']")
            page.wait_for_load_state("domcontentloaded")
            return bool(page.query_selector("select[name='breaking']"))

        for target in options:
            if threshold and state.energy < threshold:
                _flush_fails()
                state.add_log(f"Energy {state.energy}% dropped below threshold {threshold}% — stopping.")
                return

            if not _ensure_dropdown():
                _flush_fails()
                state.add_log("Breaking & Entering: lost dropdown mid-loop. Aborting.")
                return

            page.select_option("select[name='breaking']", value=target)
            page.click("input[type='submit'][name='B1'][value='Commit Crime']")
            page.wait_for_load_state("domcontentloaded")
            _refresh_state(state)

            result_soup = BeautifulSoup(page.content(), "html.parser")

            success_div = result_soup.find("div", id="success")
            if success_div:
                msg = success_div.get_text(strip=True)
                _flush_fails()
                state.add_log(f"B&E success vs {target}: {msg}")
                amounts = re.findall(r"\$([\d,]+)", msg)
                stolen = int(amounts[0].replace(",", "")) if amounts else 0
                if stolen > 0:
                    state._last_crime_victim = target
                    state._last_crime_amount = stolen
                    state.add_log(f"Stolen: ${stolen:,} from {target}")
                return

            fail_div = result_soup.find("div", id="fail")
            if fail_div:
                fail_msg = fail_div.get_text(strip=True)
                fail_counts[fail_msg] = fail_counts.get(fail_msg, 0) + 1

                if "failed" in fail_msg.lower():
                    state.record_agg_fail()
                    _flush_fails()
                    _nav(_u("/loggedin.asp?display=play"), state)
                    return

                # Soft fail (no apartment, recently survived, etc.) — go back, next target
                page.go_back(wait_until="domcontentloaded")
                continue

        _flush_fails()
        state._agg_targets_exhausted = True
        state.add_log("Breaking & Entering: all targets exhausted.")
    finally:
        page.set_extra_http_headers({})


def handle_do_crime(action: Action, state: GameState):
    crime = action.params["crime"]
    if crime == "breaking":
        handle_breaking_entering(action, state)
        return

    threshold = action.params.get("threshold", 0)
    page = browser.page()

    if crime in ONLINE_CRIMES:
        targets = _get_online_local_players(state)
        state.add_log(f"Online local targets: {len(targets)}")
    else:
        targets = _get_city_residents(state.current_city, state.own_name)
        state.add_log(f"City resident targets: {len(targets)}")

    if not targets:
        state.add_log(f"No targets found for {crime}, skipping.")
        state._agg_targets_exhausted = True
        return

    if not _nav_to_target_input(crime, state):
        if not _check_cs_punishment(state):
            state.add_log("Target input not found after crime selection. Aborting.")
        return
    if not _check_session(state):
        return
    if state.in_jail:
        state.add_log("In jail — aborting crime.")
        return
    state.add_log(f"Selected crime: {crime}")

    failed_transfers: set = set()
    fail_counts: dict = {}

    def _flush_fails():
        if not fail_counts:
            return
        total = sum(fail_counts.values())
        parts = ", ".join(f"{n}x {msg}" for msg, n in fail_counts.items())
        state.add_log(f"Crime run: {total} fail{'s' if total != 1 else ''} — {parts} (fail count: {state.agg_fail_count()}/3)")
        fail_counts.clear()

    for player in targets:
        if player in failed_transfers:
            continue

        if threshold and state.energy < threshold:
            _flush_fails()
            state.add_log(f"Energy {state.energy}% dropped below threshold {threshold}% — stopping.")
            return

        if not page.query_selector(_TARGET_INPUT):
            if not _back_to_target_input(crime, state):
                _flush_fails()
                state.add_log("Lost target input mid-loop. Aborting.")
                return

        page.fill(_TARGET_INPUT, player)
        page.click("input[type='submit'][name='B1']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)

        result_soup = BeautifulSoup(page.content(), "html.parser")

        success_div = result_soup.find("div", id="success")
        if success_div:
            msg = success_div.get_text(strip=True)
            _flush_fails()
            state.add_log(f"Crime success vs {player}: {msg}")
            amounts = re.findall(r"\$([\d,]+)", msg)
            stolen = int(amounts[0].replace(",", "")) if amounts else 0
            if stolen > 0:
                state._last_crime_victim = player
                state._last_crime_amount = stolen
                state.add_log(f"Stolen: ${stolen:,} from {player}")
            return

        fail_div = result_soup.find("div", id="fail")
        if fail_div:
            fail_msg = fail_div.get_text(strip=True)
            if "failed" in fail_msg.lower():
                state.record_agg_fail()
            fail_counts[fail_msg] = fail_counts.get(fail_msg, 0) + 1
            if "weapon" in fail_msg.lower():
                continue
            if crime == "hack" and "increased security" in fail_msg.lower():
                continue
            if crime == "hack" and "no money in their account" in fail_msg.lower():
                state.add_log(f"No money in {player}'s account — sending $1 to unlock, then retrying.")
                if not _back_to_target_input(crime, state):
                    _flush_fails()
                    state.add_log("Lost target input after no-money fail. Aborting.")
                    return
                ok = _do_transfer(player, 1, state)
                if not ok:
                    state.add_log(f"Transfer to {player} failed — skipping for this run.")
                    failed_transfers.add(player)
                    if not _nav_to_target_input(crime, state):
                        _flush_fails()
                        state.add_log("Could not return to crime page. Aborting.")
                        return
                    continue
                if not _nav_to_target_input(crime, state):
                    _flush_fails()
                    state.add_log("Could not return to crime page after transfer. Aborting.")
                    return
                page.fill(_TARGET_INPUT, player)
                page.click("input[type='submit'][name='B1']")
                page.wait_for_load_state("domcontentloaded")
                _refresh_state(state)
                retry_soup = BeautifulSoup(page.content(), "html.parser")
                success_div = retry_soup.find("div", id="success")
                if success_div:
                    msg = success_div.get_text(strip=True)
                    _flush_fails()
                    state.add_log(f"Crime success vs {player} (retry): {msg}")
                    amounts = re.findall(r"\$([\d,]+)", msg)
                    stolen = int(amounts[0].replace(",", "")) if amounts else 0
                    if stolen > 0:
                        state._last_crime_victim = player
                        state._last_crime_amount = stolen
                        state.add_log(f"Stolen: ${stolen:,} from {player}")
                    return
                retry_fail = retry_soup.find("div", id="fail")
                if retry_fail:
                    retry_msg = retry_fail.get_text(strip=True)
                    fail_counts[retry_msg] = fail_counts.get(retry_msg, 0) + 1
                continue
            if crime in ("pickpocket", "mugging", "breaking") and "recently survived" in fail_msg.lower():
                continue
            if "doesn't exist" in fail_msg.lower() or "does not exist" in fail_msg.lower():
                continue
            _flush_fails()
            _nav(_u("/loggedin.asp?display=play"), state)
            return

    _flush_fails()
    state._agg_targets_exhausted = True
    state.add_log("All targets exhausted.")


def _interact_nav(crime: str, state: GameState) -> bool:
    """Navigate to agcrime.asp and select a crime for a single manual target.

    Like _nav_to_target_input but WITHOUT the side effect of disabling the
    aggravated-crimes automation when the crime isn't currently on the list —
    a one-off manual attempt must never touch the user's config.
    Returns True if the text target input is present.
    """
    page = browser.page()
    _nav(_u("/income/agcrime.asp"), state)
    if not page.query_selector(f"input[name='agcrime'][value='{crime}']"):
        return False
    page.check(f"input[name='agcrime'][value='{crime}']")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    return bool(page.query_selector(_TARGET_INPUT))


def _interact_simple_crime(crime: str, target: str, state: GameState) -> dict:
    """One-shot pickpocket / mugging / hack against a single named target."""
    page = browser.page()
    if not _interact_nav(crime, state):
        if _check_cs_punishment(state):
            return {"ok": False, "message": f"Community service required before {crime}."}
        return {"ok": False, "message": f"'{crime}' is not available right now."}
    if not _check_session(state):
        return {"ok": False, "message": "Session expired — will re-login."}

    page.fill(_TARGET_INPUT, target)
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    soup = BeautifulSoup(page.content(), "html.parser")
    success_div = soup.find("div", id="success")
    if success_div:
        msg = success_div.get_text(strip=True)
        state.add_log(f"Interact {crime} vs {target}: {msg}")
        amounts = re.findall(r"\$([\d,]+)", msg)
        if amounts:
            state._last_crime_victim = target
            state._last_crime_amount = int(amounts[0].replace(",", ""))
        return {"ok": True, "message": msg}

    fail_div = soup.find("div", id="fail")
    if fail_div:
        msg = fail_div.get_text(strip=True)
        if "failed" in msg.lower():
            state.record_agg_fail()
        state.add_log(f"Interact {crime} vs {target}: {msg}")
        _nav(_u("/loggedin.asp?display=play"), state)
        return {"ok": False, "message": msg}

    return {"ok": False, "message": "No result parsed from the crime page."}


def _interact_breaking(target: str, state: GameState) -> dict:
    """One-shot Breaking & Entering against a single named target (mobile UA)."""
    page = browser.page()
    page.set_extra_http_headers({"User-Agent": _MOBILE_UA})
    try:
        _nav(_u("/income/agcrime.asp"), state)
        if not _check_session(state):
            return {"ok": False, "message": "Session expired — will re-login."}
        if not page.query_selector("input[name='agcrime'][value='breaking']"):
            if _check_cs_punishment(state):
                return {"ok": False, "message": "Community service required before B&E."}
            return {"ok": False, "message": "Breaking & Entering is not available right now."}
        page.check("input[name='agcrime'][value='breaking']")
        page.click("input[type='submit'][name='B1']")
        page.wait_for_load_state("domcontentloaded")

        soup = BeautifulSoup(page.content(), "html.parser")
        select = soup.find("select", {"name": "breaking"})
        if not select:
            if _check_cs_punishment(state):
                return {"ok": False, "message": "Community service required before B&E."}
            return {"ok": False, "message": "No B&E target list available."}

        # Match the target by the option's visible text (owner name); fall back
        # to the value if the game keys options by name directly.
        match_val = None
        for o in select.find_all("option"):
            val = o.get("value")
            if not val:
                continue
            if o.get_text(strip=True).lower() == target.lower() or val.lower() == target.lower():
                match_val = val
                break
        if match_val is None:
            return {"ok": False, "message": f"{target} has no burglable apartment here."}

        page.select_option("select[name='breaking']", value=match_val)
        page.click("input[type='submit'][name='B1'][value='Commit Crime']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)

        soup = BeautifulSoup(page.content(), "html.parser")
        success_div = soup.find("div", id="success")
        if success_div:
            msg = success_div.get_text(strip=True)
            state.add_log(f"Interact B&E vs {target}: {msg}")
            amounts = re.findall(r"\$([\d,]+)", msg)
            if amounts:
                state._last_crime_victim = target
                state._last_crime_amount = int(amounts[0].replace(",", ""))
            return {"ok": True, "message": msg}
        fail_div = soup.find("div", id="fail")
        if fail_div:
            msg = fail_div.get_text(strip=True)
            if "failed" in msg.lower():
                state.record_agg_fail()
            state.add_log(f"Interact B&E vs {target}: {msg}")
            return {"ok": False, "message": msg}
        return {"ok": False, "message": "No result parsed from the B&E page."}
    finally:
        page.set_extra_http_headers({})


def handle_interact(action: Action, state: GameState):
    """Single manual player interaction requested from the Active players tab.
    Puts a {"ok", "message"} dict on the result queue."""
    rq = action.params.get("result_queue")
    crime  = action.params.get("crime", "")
    target = action.params.get("target", "")
    amount = int(action.params.get("amount", 0) or 0)

    def _reply(d):
        if rq is not None:
            rq.put(d)

    if not state.logged_in:
        _reply({"ok": False, "message": "Not logged in."})
        return
    if state.in_jail or state.in_hospital:
        _reply({"ok": False, "message": "Cannot act while in jail or hospital."})
        return
    if not target:
        _reply({"ok": False, "message": "No target specified."})
        return

    try:
        if crime == "transfer":
            if amount <= 0:
                _reply({"ok": False, "message": "Enter an amount greater than 0."})
                return
            ok = _do_transfer(target, amount, state)
            msg = (f"Transferred ${amount:,} to {target}." if ok
                   else f"Transfer of ${amount:,} to {target} failed.")
            state.add_log(f"Interact: {msg}")
            _reply({"ok": ok, "message": msg})
            return
        if crime == "breaking":
            _reply(_interact_breaking(target, state))
            return
        if crime in ("pickpocket", "mugging", "hack"):
            _reply(_interact_simple_crime(crime, target, state))
            return
        _reply({"ok": False, "message": f"Unknown interaction '{crime}'."})
    except Exception as e:
        state.add_log(f"Interact error ({crime} vs {target}): {e}")
        _reply({"ok": False, "message": f"Error: {e}"})


def handle_check_weapon(action: Action, state: GameState):
    crime = action.params["crime"]
    page = browser.page()
    page.goto(_u("/profile/default.asp"), wait_until="load", timeout=30000)
    parse_state(page.content(), browser.current_url(), state)

    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    weapons_div = soup.find("div", class_="showWeapons")
    if not weapons_div:
        state.add_log("Could not find weapons div.")
        return

    tables = weapons_div.find_all("table", class_="item_table")
    equipped_names = set()
    stash_slots = []

    for table in tables:
        header = table.find("div", style=lambda s: s and "ff9900" in s)
        if not header:
            continue
        slot_label = header.get_text(strip=True)
        item_td = table.find("td", class_="item_content")
        if not item_td:
            continue
        b_tag = item_td.find("b")
        if not b_tag:
            continue
        weapon_name = b_tag.get_text(strip=True)

        action_td = table.find("td", class_="item_content", align="center")
        if not action_td:
            tds = table.find_all("td", class_="item_content")
            action_td = tds[-1] if tds else None

        if "Hand" in slot_label:
            equipped_names.add(weapon_name)
        elif "Stash" in slot_label:
            carry_link = None
            if action_td:
                for a in action_td.find_all("a"):
                    if "Carry" in a.get_text() or "use" in a.get("href", ""):
                        carry_link = urls.BASE_URL + a["href"]
                        break
            if carry_link:
                stash_slots.append((weapon_name, carry_link))

    def _is_valid(name):
        if crime == "mugging":
            return name in MUGGING_WEAPONS
        return name not in BODY_PARTS

    if any(_is_valid(w) for w in equipped_names):
        state.add_log(f"Valid weapon already equipped for {crime}.")
        return

    for (wname, carry_url) in stash_slots:
        if _is_valid(wname):
            state.add_log(f"Equipping {wname} for {crime}.")
            browser.navigate(carry_url)
            _refresh_state(state)
            return

    state.add_log(f"No valid weapon found for {crime}.")

    state.add_log(f"No valid weapon found for {crime}. Skipping crime.")
    # Signal crime task to skip by marking no weapon — handled by AggCrimeTask resetting




_CONSUMABLE_NAMES = {
    "marijuana": "Marijuana",
    "cocaine":   "Cocaine",
    "ecstasy":   "Ecstasy",
    "acid":      "Acid",
    "speed":     "Speed",
    "pice":      "P / Ice",
    "heroin":    "Heroin",
}


def handle_consume(action: Action, state: GameState):
    consume_type = action.params["type"]
    count = int(action.params.get("count", 1))
    url = _u(f"/profile/consumables.asp?action=consume&type={consume_type}")
    display_name = _CONSUMABLE_NAMES.get(consume_type, consume_type.title())

    successes = 0
    failures = 0

    for i in range(count):
        _nav(url, state)

        if "profile/default.asp" in browser.current_url():
            successes += 1
            if count == 1:
                state.add_log(f"Consume {display_name}: You successfully consumed the {display_name}!")
            continue

        soup = BeautifulSoup(browser.page().content(), "html.parser")
        msg_div = soup.find("div", id="success") or soup.find("div", id="fail")
        msg = msg_div.get_text(strip=True) if msg_div else "No result."
        if msg_div and msg_div.get("id") == "success":
            successes += 1
        else:
            failures += 1
        if count == 1:
            state.add_log(f"Consume {display_name}: {msg}")

    if count > 1:
        summary = f"You successfully used {successes} x {display_name}."
        if failures:
            summary += f" ({failures} failed)"
        state.add_log(f"Consume {display_name}: {summary}")


def handle_refresh_state(action: Action, state: GameState):
    if state.in_jail:
        _nav(_u("/jail/contraband.asp"), state)
    else:
        _nav(_u("/loggedin.asp?display=play"), state)


def handle_payback(action: Action, state: GameState):
    amount = action.params["amount"]
    target = action.params["target"]
    page = browser.page()

    _nav(_u("/income/bank.asp?option=transfers"), state)
    if not _check_session(state):
        return

    page.fill("input[name='transferamount']", str(amount))
    page.fill("input[name='transfername']", target)
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded")

    soup = BeautifulSoup(page.content(), "html.parser")
    result_text = soup.get_text()

    if "Your transfer was blocked due to possible spam!" in result_text:
        state.add_log(f"Payback to {target} blocked as spam — skipping.")
        return

    _refresh_state(state)
    state.add_log(f"Payback sent: ${amount:,} to {target}.")


def handle_crossroad(action: Action, state: GameState):
    """Resolve a Career Crossroad page.

    The page offers two radios: the first is the *current* career, the second the
    *new* career. Picks per the configured selection and submits."""
    selection = action.params.get("selection", "current")
    page = browser.page()
    if "crossroad.asp" not in browser.current_url():
        return

    radios = page.query_selector_all("input[name='option']")
    if len(radios) < 2:
        state.add_log(f"Career crossroad: expected 2 options, found {len(radios)} — skipping.")
        return

    idx = 0 if selection == "current" else 1
    soup = BeautifulSoup(page.content(), "html.parser")
    label_el = soup.find("label", {"for": "one" if idx == 0 else "two"})
    career = label_el.get_text(strip=True) if label_el else ("current" if idx == 0 else "new")

    radios[idx].click()
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log(f"Career crossroad: chose {'current' if idx == 0 else 'new'} career ({career}).")


def handle_probe_agcrime(action: Action, state: GameState):
    """Navigate to agcrime.asp — if it redirects, CS is still required; if it loads, CS is done."""
    _nav(_u("/income/agcrime.asp"), state)
    url = browser.current_url()
    if "/income/agcrime.asp" in url:
        # Loaded fine — CS no longer blocking
        state.cs_sentence = 0
    else:
        # Redirected — still blocked; refresh sentence count from page
        _check_cs_punishment(state)


def handle_community_service(action: Action, state: GameState):
    in_home = action.params["in_home_city"]
    page = browser.page()
    _nav(_u("/income/communityservice.asp"), state)

    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")

    if in_home:
        options = soup.find_all("input", attrs={"name": "comservice", "type": "radio"})
        if not options:
            state.add_log("No community service options found.")
            return
        last = options[-1]
        page.check(f"input[name='comservice'][value='{last['value']}']")
        state.add_log(f"Community service (home city): {last['value']}")
    else:
        options = soup.find_all("input", attrs={"name": "csinothercities", "type": "radio"})
        if not options:
            state.add_log("No community service options found (away city).")
            return
        last = options[-1]
        page.check(f"input[name='csinothercities'][value='{last['value']}']")
        state.add_log(f"Community service (away city): {last['value']}")

    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)


_DOG_TRAIN_VALUES = {"walkdog", "throwstick", "givebone"}


def handle_do_dog_trains(action: Action, state: GameState):
    """Dog trains — reuses the community-service page. Picks a random dog option.
    If the player has no dog, disables the relevant toggle by context."""
    import random
    context = action.params.get("context", "home")  # "home" | "away"
    page = browser.page()
    _nav(_u("/income/communityservice.asp"), state)
    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    options = [o for o in soup.find_all("input", attrs={"name": "comservice", "type": "radio"})
               if o.get("value") in _DOG_TRAIN_VALUES]

    if not options:
        msg = "Dog trains: no dog options found — player has no dog."
        state.add_log(msg)
        c = cfg.load()
        if context == "away":
            c.setdefault("away_action", {})["type"] = ""
            state.add_log("Dog trains: away action set to None.")
        else:
            c.setdefault("action", {})["enabled"] = False
            state.add_log("Dog trains: actions disabled.")
        cfg.save(c)
        _notify(state, "dog_trains_unavailable", msg)
        return

    choice = random.choice(options)
    val = choice.get("value", "")
    page.check(f"input[name='comservice'][value='{val}']")
    state.add_log(f"Dog trains: {val}")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)


def handle_fire_duties(action: Action, state: GameState):
    page = browser.page()
    _nav(_u("/income/fireduties.asp"), state)

    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    options = soup.find_all("input", attrs={"name": "comservice", "type": "radio"})
    if not options:
        state.add_log("No fire duties options found.")
        return

    last = options[-1]
    page.check(f"input[name='comservice'][value='{last['value']}']")
    state.add_log(f"Fire duties: {last['value']}")

    page.click("input[type='submit'][name='B2']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)


def _action_fallback(state: GameState, reason: str):
    c = cfg.load()
    fallback = c.get("action", {}).get("fallback_action", "")
    if fallback:
        c["action"]["type"] = fallback
        c["action"]["sub_option"] = ""
        c["action"]["fallback_action"] = ""
        cfg.save(c)
        import settings_rev; settings_rev.bump()
        state.add_log(f"{reason} — switched action to '{fallback}'.")
    else:
        c["action"]["enabled"] = False
        cfg.save(c)
        state.add_log(f"{reason} — disabling actions.")


def handle_career_training(action: Action, state: GameState):
    url = action.params["url"]
    career = action.params["career"]
    page = browser.page()
    _nav(url, state)

    if not _check_session(state):
        return

    # Redirect to local.asp means the training centre is unavailable
    if "/localcity/local.asp" in browser.current_url():
        soup = BeautifulSoup(page.content(), "html.parser")
        fail = soup.find("div", id="fail") or soup.find("div", class_="info red")
        msg = fail.get_text(strip=True) if fail else "Training centre unavailable."
        _action_fallback(state, f"Career training: {msg}")
        return

    soup = BeautifulSoup(page.content(), "html.parser")

    # Parse current training count from page text e.g. "Current Customs trains: 4"
    import re as _re
    page_text = soup.get_text(" ")
    train_match = _re.search(r"Current \w+ trains?:\s*(\d+)", page_text, _re.I)
    current_trains = int(train_match.group(1)) if train_match else None
    if current_trains is not None:
        state.add_log(f"Career training ({career}): current trains = {current_trains}.")

    # Stop-at-14 check
    stop_at_14 = cfg.load().get("action", {}).get("career_training_stop_at_14", False)
    if stop_at_14 and current_trains is not None and current_trains >= 14:
        _action_fallback(state, f"Career training: reached {current_trains} trains (stop-at-14)")
        return

    select = soup.find("select", attrs={"name": "action"})
    if not select:
        state.add_log(f"Career training form not found for {career}.")
        return

    options = select.find_all("option")
    enroll_opt = None
    study_opt = None
    for opt in options:
        val = opt.get("value", "")
        text = opt.get_text(strip=True).lower()
        if val == "Yes" or "continue" in text or "study" in text:
            study_opt = val
        if "accept" in val or "begin training" in text:
            enroll_opt = val

    chosen = study_opt or enroll_opt
    if not chosen:
        state.add_log(f"No valid training option found for {career}.")
        return

    page.select_option("select[name='action']", chosen)
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log(f"Career training submitted for {career}.")


def handle_university(action: Action, state: GameState):
    import re as _re
    from tasks.university import DEGREES as _DEGREES
    url = action.params["url"]
    degree_cfg = action.params.get("degree", "")  # empty = all degrees in order
    page = browser.page()
    _nav(url, state)

    if not _check_session(state):
        return

    def _submit(value: str):
        page.select_option("select[name='action']", value)
        page.click("input[type='submit'][name='B1']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)

    # Walk the university flow in one run: select degree → accept enrollment → study.
    # Each stage re-parses the resulting page so we don't rely on separate task cycles.
    for _step in range(4):
        soup = BeautifulSoup(page.content(), "html.parser")
        select = soup.find("select", attrs={"name": "action"})
        if not select:
            state.add_log("University: form not found.")
            return
        options = {opt.get("value", ""): opt.get_text(strip=True) for opt in select.find_all("option")}

        # --- Studying page: already enrolled, just study ---
        if "Yes" in options:
            _submit("Yes")
            soup2 = BeautifulSoup(page.content(), "html.parser")
            page_text = soup2.get_text(" ").lower()
            if any(w in page_text for w in ("congratulations", "completed", "graduated", "degree awarded")):
                degree_match = _re.search(r"degree in (\w+)", page_text, _re.I)
                completed_name = degree_match.group(1).capitalize() if degree_match else None
                if completed_name:
                    canonical = next((d for d in _DEGREES if d.lower() == completed_name.lower()), completed_name)
                    c = cfg.load()
                    completed = c.setdefault("university", {}).setdefault("completed", [])
                    if canonical not in completed:
                        completed.append(canonical)
                        cfg.save(c)
                    state.add_log(f"University: completed {canonical} degree.")
            else:
                state.add_log("University: studied.")
            return

        # --- Enrollment confirmation page: accept the degree ---
        accept_val = next((v for v in options if v.lower().startswith("accept")), None)
        if accept_val:
            page_text = soup.get_text(" ")
            fee_match = _re.search(r"\$([0-9,]+)", page_text)
            if fee_match:
                fee = int(fee_match.group(1).replace(",", ""))
                if (state.clean_money or 0) < fee:
                    needed = fee - (state.clean_money or 0)
                    state.add_log(f"University: need ${fee:,} to enroll, withdrawing ${needed:,}.")
                    handle_withdraw(Action("withdraw", amount=needed), state)
                    if (state.clean_money or 0) < fee:
                        state.add_log("University: insufficient funds after withdrawal — skipping.")
                        return
            _submit(accept_val)
            state.add_log(f"University: enrolled ({accept_val}).")
            continue  # re-parse — should now be the studying page

        # --- Initial selection page: pick the degree to study ---
        c = cfg.load()
        completed = c.get("university", {}).get("completed", [])
        if degree_cfg:
            canonical = next(
                (d for d in _DEGREES
                 if d.lower() == degree_cfg.lower() or d.lower()[:5] == degree_cfg.lower()[:5]),
                degree_cfg,
            )
            if canonical in completed:
                _action_fallback(state, f"University: '{canonical}' already completed")
                return
        else:
            canonical = next((d for d in _DEGREES if d not in completed), None)
            if canonical is None:
                _action_fallback(state, "University: all degrees completed")
                return

        match = next(
            (v for v in options
             if v.lower() == canonical.lower() or options[v].lower() == canonical.lower()),
            None,
        )
        if not match:
            _action_fallback(state, f"University: degree '{canonical}' not available on selector")
            return
        _submit(match)
        state.add_log(f"University: selected {canonical} course.")
        continue  # re-parse — should now be the enrollment confirmation page


def handle_training_centre(action: Action, state: GameState):
    from tasks.training_centre import TRAINING_COSTS
    import re as _re
    discipline = action.params["discipline"]
    url = action.params["url"]
    cost = TRAINING_COSTS.get(discipline, 0)
    page = browser.page()
    _nav(url, state)

    if not _check_session(state):
        return

    if "/localcity/local.asp" in browser.current_url():
        soup = BeautifulSoup(page.content(), "html.parser")
        fail = soup.find("div", id="fail") or soup.find("div", class_="info red")
        msg = fail.get_text(strip=True) if fail else "Training centre unavailable."
        _action_fallback(state, f"Training centre: {msg}")
        return

    soup = BeautifulSoup(page.content(), "html.parser")

    holder = soup.find("div", id="holder_content")
    if holder and "no more training to complete" in holder.get_text(" ").lower():
        _action_fallback(state, "Training centre: no more training to complete")
        return

    select = soup.find("select", attrs={"name": "action"})
    if not select:
        state.add_log("Training centre: form not found.")
        return

    options = {opt.get("value", ""): opt.get_text(strip=True) for opt in select.find_all("option")}

    # Already training page: "Yes, I would like to train"
    if "Yes" in options and discipline not in options:
        page.select_option("select[name='action']", "Yes")
        page.click("input[type='submit'][name='B1']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)
        state.add_log(f"Training centre: continued training in {discipline}.")
        return

    # Enrollment confirmation page (accept option present) — ensure funds, enrol, then re-nav
    accept_val = next((v for v in options if v.startswith("accept")), None)
    if accept_val:
        if (state.clean_money or 0) < cost:
            min_cash = int(cfg.load().get("misc", {}).get("min_cash_on_hand", 0))
            needed = cost - (state.clean_money or 0) + min_cash
            state.add_log(f"Training centre: need ${cost:,}, withdrawing ${needed:,}.")
            handle_withdraw(Action("withdraw", amount=needed), state)
            if (state.clean_money or 0) < cost:
                state.add_log("Training centre: insufficient funds after withdrawal — skipping.")
                return
            _nav(url, state)
        page.select_option("select[name='action']", accept_val)
        page.click("input[type='submit'][name='B1']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)
        state.add_log(f"Training centre: enrolled in {discipline}.")
        return

    # Page 1: discipline selection — pick the configured discipline
    if discipline in options:
        page.select_option("select[name='action']", discipline)
        page.click("input[type='submit'][name='B1']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)

        # Now on the confirmation page — ensure funds, enrol
        soup2 = BeautifulSoup(page.content(), "html.parser")
        select2 = soup2.find("select", attrs={"name": "action"})
        if select2:
            accept_val2 = next(
                (opt.get("value", "") for opt in select2.find_all("option")
                 if opt.get("value", "").startswith("accept")),
                None,
            )
            if accept_val2:
                if (state.clean_money or 0) < cost:
                    min_cash = int(cfg.load().get("misc", {}).get("min_cash_on_hand", 0))
                    needed = cost - (state.clean_money or 0) + min_cash
                    state.add_log(f"Training centre: need ${cost:,}, withdrawing ${needed:,}.")
                    handle_withdraw(Action("withdraw", amount=needed), state)
                    if (state.clean_money or 0) < cost:
                        state.add_log("Training centre: insufficient funds after withdrawal — skipping.")
                        return
                    _nav(url, state)
                page.select_option("select[name='action']", accept_val2)
                page.click("input[type='submit'][name='B1']")
                page.wait_for_load_state("domcontentloaded")
                _refresh_state(state)
                state.add_log(f"Training centre: enrolled in {discipline}.")
                return
            else:
                state.add_log("Training centre: no accept option found on confirmation page.")
                return
        state.add_log(f"Training centre: submitted {discipline}.")
        return

    _action_fallback(state, f"Training centre: discipline '{discipline}' not available in selector")


def _do_transfer(recipient: str, amount: int, state: GameState) -> bool:
    """Returns True if transfer succeeded, False otherwise."""
    page = browser.page()
    _nav(_u("/income/bank.asp?option=transfers"), state)
    if not _check_session(state):
        return False
    page.fill("input[name='transferamount']", str(amount))
    page.fill("input[name='transfername']", recipient)
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    soup = BeautifulSoup(page.content(), "html.parser")
    success = soup.find("div", id="success")
    if success:
        state.add_log(f"Transfer sent: ${amount:,} to {recipient}.")
        return True
    fail = soup.find("div", id="fail")
    msg = fail.get_text(strip=True) if fail else "Unknown error"
    state.add_log(f"Transfer failed to {recipient}: {msg}")
    return False


def _get_public_business_owner(business_name: str, state: GameState) -> "str | None":
    job = PUBLIC_JOB_MAP.get(business_name)
    if not job:
        # Loosen to city-prefixed names, e.g. "Auckland Bank Tills" → "Bank Tills"
        matched = _match_public_business(business_name, PUBLIC_JOB_MAP.keys())
        job = PUBLIC_JOB_MAP.get(matched) if matched else None
    if not job:
        state.add_log(f"No job mapping for {business_name}.")
        return None
    # The owner is whoever holds the top job in the city where the robbery
    # was performed (the bot's current city), not necessarily its home city.
    city = state.current_city or state.home_city
    browser.page().goto(_u("/skin/updateusers.php?q=1"), wait_until="domcontentloaded", timeout=15000)
    try:
        data = json.loads(browser.page().inner_text("body"))
    except Exception:
        state.add_log("Failed to parse users for public business payback.")
        return None
    owner = next(
        (p["userName"] for p in data
         if p.get("userHomeCity") == city and p.get("userOccupation") == job),
        None,
    )
    if not owner:
        state.add_log(f"No {job} found in {city} for payback.")
    return owner


def _get_private_business_owner(business_name: str, state: GameState) -> "str | None":
    _nav(_u("/business/business.asp"), state)
    soup = BeautifulSoup(browser.page().content(), "html.parser")
    for row in soup.select("table tr"):
        cells = row.find_all("td", class_="display_border")
        if len(cells) >= 2 and cells[0].get_text(strip=True) == business_name:
            a = cells[1].find("a")
            if a:
                return a.get_text(strip=True)
            break
    state.add_log(f"Owner of {business_name} not found (may be Hidden).")
    return None


def handle_armed_robbery(action: Action, state: GameState):
    agg_private = action.params.get("agg_private", False)
    agg_drug_house = action.params.get("agg_drug_house", False)
    threshold = action.params.get("threshold", 0)

    page = browser.page()

    # Navigate to agcrime.asp and submit the armed robbery form
    _nav(_u("/income/agcrime.asp"), state)
    if not _check_session(state):
        return
    if state.in_jail:
        state.add_log("In jail — aborting armed robbery.")
        return
    if threshold and state.energy < threshold:
        state.add_log(f"Energy {state.energy}% dropped below threshold {threshold}% — aborting.")
        return
    if not page.query_selector("input[name='agcrime'][value='armed']"):
        if not _check_cs_punishment(state):
            state.add_log("Armed crime option not available — aborting.")
        return
    page.check("input[name='agcrime'][value='armed']")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    if state.in_hospital:
        state.add_log("Armed robbery: redirected to hospital — injured by falling debris. Tasks paused until release.")
        return

    if _check_cs_punishment(state):
        return

    check_other_tasks = action.params.get("check_other_tasks")
    pass_num = 0

    while True:
        pass_num += 1
        for attempt in range(ARMED_MAX_RETRIES):
            if attempt > 0 or pass_num > 1:
                time.sleep(5)
                page.once("dialog", lambda d: d.accept())
                page.reload(wait_until="domcontentloaded")
                _refresh_state(state)

            soup = BeautifulSoup(page.content(), "html.parser")
            select = soup.find("select", attrs={"name": "armed"})
            if not select:
                state.add_log("Armed robbery: business select not found.")
                _nav(_u("/loggedin.asp?display=play"), state)
                return

            target = None
            for option in select.find_all("option"):
                raw = option.get_text(strip=True)
                value = option.get("value", "")
                if not value or raw.startswith("Please"):
                    continue
                if "*" not in raw:
                    continue
                name = raw.rstrip("*").strip()
                is_public = _match_public_business(name, PUBLIC_BUSINESSES) is not None
                is_drug_house = name == "Drug House"
                is_private = not is_public

                if is_drug_house and not agg_drug_house:
                    continue
                if is_private and not is_drug_house and not agg_private:
                    continue
                target = (value, name, is_public, is_drug_house)
                break

            if target:
                value, name, is_public, is_drug_house = target
                page.select_option("select[name='armed']", value)
                page.click("input[type='submit'][name='B1']")
                page.wait_for_load_state("domcontentloaded")
                _refresh_state(state)

                if state.in_hospital:
                    state.add_log("Armed robbery: redirected to hospital — injured by falling debris. Tasks paused until release.")
                    return

                result_soup = BeautifulSoup(page.content(), "html.parser")
                success_div = result_soup.find("div", id="success")
                if success_div:
                    msg = success_div.get_text(strip=True)
                    state.add_log(f"Armed robbery success ({name}): {msg}")
                    amounts = re.findall(r"\$([\d,]+)", msg)
                    stolen = int(amounts[0].replace(",", "")) if amounts else 0
                    if stolen > 0:
                        owner = None
                        if is_public:
                            owner = _get_public_business_owner(name, state)
                        elif is_private and not is_drug_house:
                            owner = _get_private_business_owner(name, state)
                        if owner:
                            state._last_crime_victim = owner
                            state._last_crime_amount = stolen
                    return

                fail_div = result_soup.find("div", id="fail")
                if fail_div:
                    fail_msg = fail_div.get_text(strip=True)
                    if "failed" in fail_msg.lower():
                        state.record_agg_fail()
                    state.add_log(f"Armed robbery failed: {fail_msg}")
                else:
                    state.add_log("Armed robbery: unexpected result page.")
                _nav(_u("/loggedin.asp?display=play"), state)
                return

        # retries exhausted — check if another task needs to run
        state.add_log(f"Armed robbery: no valid target after {ARMED_MAX_RETRIES} attempts (pass {pass_num}). Checking task queue...")
        if check_other_tasks and check_other_tasks():
            state.add_log("Another task is ready — yielding armed robbery.")
            _nav(_u("/loggedin.asp?display=play"), state)
            return
        state.add_log("No other tasks pending — retrying armed robbery.")


def handle_torch_business(action: Action, state: GameState):
    torch_private = action.params.get("torch_private", False)
    torch_payback_public = action.params.get("torch_payback_public", "everyone")
    torch_payback_private = action.params.get("torch_payback_private", "everyone")
    threshold = action.params.get("threshold", 0)

    page = browser.page()

    _nav(_u("/income/agcrime.asp"), state)
    if not _check_session(state):
        return
    if state.in_jail:
        state.add_log("In jail — aborting torch business.")
        return
    if threshold and state.energy < threshold:
        state.add_log(f"Energy {state.energy}% dropped below threshold {threshold}% — aborting.")
        return
    if not page.query_selector("input[name='agcrime'][value='torchbusiness']"):
        if not _check_cs_punishment(state):
            state.add_log("Torch business option not available — aborting.")
        return
    page.check("input[name='agcrime'][value='torchbusiness']")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    if state.in_hospital:
        state.add_log("Torch business: redirected to hospital. Tasks paused until release.")
        return

    if _check_cs_punishment(state):
        return

    check_other_tasks = action.params.get("check_other_tasks")
    pass_num = 0

    while True:
        pass_num += 1
        for attempt in range(ARMED_MAX_RETRIES):
            if attempt > 0 or pass_num > 1:
                time.sleep(5)
                page.once("dialog", lambda d: d.accept())
                page.reload(wait_until="domcontentloaded")
                _refresh_state(state)

            soup = BeautifulSoup(page.content(), "html.parser")
            select = soup.find("select", attrs={"name": "torchb"})
            if not select:
                state.add_log("Torch business: target select not found.")
                _nav(_u("/loggedin.asp?display=play"), state)
                return

            target = None
            for option in select.find_all("option"):
                raw = option.get_text(strip=True)
                value = option.get("value", "")
                if not value or raw.startswith("Please"):
                    continue
                name = raw.rstrip("*").strip()
                is_public = _match_public_business(name, TORCH_PUBLIC_BUSINESSES) is not None
                if name == "Drug House":
                    continue
                if not is_public and not torch_private:
                    continue
                target = (value, name, is_public)
                break

            if target:
                value, name, is_public = target
                page.select_option("select[name='torchb']", value)
                page.click("input[type='submit'][name='B1']")
                page.wait_for_load_state("domcontentloaded")
                _refresh_state(state)

                if state.in_hospital:
                    state.add_log("Torch business: redirected to hospital. Tasks paused until release.")
                    return

                result_soup = BeautifulSoup(page.content(), "html.parser")
                success_div = result_soup.find("div", id="success")
                if success_div:
                    msg = success_div.get_text(strip=True)
                    state.add_log(f"Torch business success ({name}): {msg}")
                    amounts = re.findall(r"\$([\d,]+)", msg)
                    stolen = int(amounts[0].replace(",", "")) if amounts else 0
                    if stolen > 0:
                        payback_mode = torch_payback_public if is_public else torch_payback_private
                        owner = None
                        if is_public:
                            owner = _get_public_business_owner(name, state)
                        else:
                            owner = _get_private_business_owner(name, state)
                        if owner:
                            state._last_crime_victim = owner
                            state._last_crime_amount = stolen
                            state._last_crime_payback_mode = payback_mode
                    return

                fail_div = result_soup.find("div", id="fail")
                if fail_div:
                    fail_msg = fail_div.get_text(strip=True)
                    if "failed" in fail_msg.lower():
                        state.record_agg_fail()
                    state.add_log(f"Torch business failed: {fail_msg}")
                else:
                    state.add_log("Torch business: unexpected result page.")
                _nav(_u("/loggedin.asp?display=play"), state)
                return

        state.add_log(f"Torch business: no valid target after {ARMED_MAX_RETRIES} attempts (pass {pass_num}). Checking task queue...")
        if check_other_tasks and check_other_tasks():
            state.add_log("Another task is ready — yielding torch business.")
            _nav(_u("/loggedin.asp?display=play"), state)
            return
        state.add_log("No other tasks pending — retrying torch business.")


def handle_drug_manufacturing(action: Action, state: GameState):
    page = browser.page()
    _nav(_u("/income/manufacture.asp"), state)

    if not _check_session(state):
        return

    if _u("/income/income.asp") in browser.current_url():
        state.add_log("Drug manufacturing redirected to income page — likely missing science degree or not in Gangster career.")
        return

    select = page.query_selector("select[name='action']")
    if not select:
        state.add_log("Drug manufacturing: action select not found on page.")
        return

    page.select_option("select[name='action']", value="Yes")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    global _drug_manufacture_cooldown_until
    result_soup = BeautifulSoup(page.content(), "html.parser")
    success_div = result_soup.find("div", id="success")
    fail_div = result_soup.find("div", id="fail")
    if success_div:
        state.add_log(f"Drug manufacturing: {success_div.get_text(strip=True)}")
    elif fail_div:
        _drug_manufacture_cooldown_until = time.monotonic() + 1800
        state.add_log(
            f"Drug manufacturing failed: {fail_div.get_text(strip=True)} "
            f"— cooling down for 30 minutes."
        )
    else:
        state.add_log("Drug manufacturing: submitted (no result div).")



_HOSPITAL_INJURY_TYPE = {
    "sex change": "sex_change",
    "bionic": "bionics",
    "flu": "flu",
    "recover": "recover",
    "dna": "dna",
}


def _hospital_injury_to_type(injury_text: str) -> str:
    t = injury_text.lower()
    for keyword, task_type in _HOSPITAL_INJURY_TYPE.items():
        if keyword in t:
            return task_type
    return "unknown"


def _save_casework_snapshot(label: str, html: str):
    import paths, os
    path = os.path.join(paths.data_dir(), f"casework_{label}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


_EARN_SEED = [
    {"label": "Whore",                               "schedule_value": "whore",              "data_earn": "0",    "category": "Secret",      "available": True,  "enabled": False},
    {"label": "Streetfight",                         "schedule_value": "street_fight",        "data_earn": "1",    "category": "Secret",      "available": True,  "enabled": False},
    {"label": "Joyride",                             "schedule_value": "joy_ride",            "data_earn": None,   "category": "Secret",      "available": None,  "enabled": False},
    {"label": "Pimp",                                "schedule_value": "pimp",               "data_earn": None,   "category": "Secret",      "available": None,  "enabled": False},
    {"label": "Shoplift",                            "schedule_value": "shoplift",            "data_earn": "2",    "category": "Crime",       "available": True,  "enabled": False},
    {"label": "Steal Cheques",                       "schedule_value": "steal_cheques",       "data_earn": None,   "category": "Crime",       "available": None,  "enabled": False},
    {"label": "Nurse at local hospital",             "schedule_value": "nurse",               "data_earn": "3",    "category": "Hospital",    "available": True,  "enabled": False},
    {"label": "Doctor at local hospital",            "schedule_value": "doctor",              "data_earn": None,   "category": "Hospital",    "available": None,  "enabled": False},
    {"label": "Surgeon at local hospital",           "schedule_value": "surgeon",             "data_earn": None,   "category": "Hospital",    "available": None,  "enabled": False},
    {"label": "Hospital Director",                   "schedule_value": "hospital_director",   "data_earn": None,   "category": "Hospital",    "available": None,  "enabled": False},
    {"label": "Mechanic at local vehicle yard",      "schedule_value": "mechanic",            "data_earn": "4",    "category": "Engineering", "available": True,  "enabled": False},
    {"label": "Technician at local vehicle yard",    "schedule_value": "technician",          "data_earn": "5",    "category": "Engineering", "available": True,  "enabled": False},
    {"label": "Engineer at local Construction Site", "schedule_value": "engineer",            "data_earn": "6",    "category": "Engineering", "available": True,  "enabled": False},
    {"label": "Work at local bank",                  "schedule_value": "bank_teller",         "data_earn": "7",    "category": "Bank",        "available": True,  "enabled": False},
    {"label": "Mortician Assistant",                 "schedule_value": "mortician_assistant", "data_earn": "8",    "category": "Mortician",   "available": True,  "enabled": False},
    {"label": "Legal Secretary",                     "schedule_value": "legal_secretary",     "data_earn": "10",   "category": "Law",         "available": True,  "enabled": False},
    {"label": "Drag racing",                         "schedule_value": "drag_racing",         "data_earn": None,   "category": "Crime",       "available": None,  "enabled": False},
    {"label": "Hack bank account",                   "schedule_value": "hack_bank",           "data_earn": None,   "category": "Crime",       "available": None,  "enabled": False},
    {"label": "Scamming",                            "schedule_value": "scamming",            "data_earn": None,   "category": "Crime",       "available": None,  "enabled": False},
    {"label": "Pizza Restaurant",                    "schedule_value": None,                  "data_earn": "Pizza","category": "General",     "available": False,  "enabled": False},
    {"label": "Local 7/11",                          "schedule_value": None,                  "data_earn": "711",  "category": "General",     "available": False,  "enabled": False},
    {"label": "Bar/Nightclub",                       "schedule_value": None,                  "data_earn": "Bar",  "category": "General",     "available": False,  "enabled": False},
]


def _upsert_earn_catalog(auto_opts, manual_opts):
    """Merge scraped earn options into the persistent catalog JSON."""
    import paths, os, json as _json

    path = os.path.join(paths.data_dir(), "available_earns.json")
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            _json.dump(list(_EARN_SEED), f, indent=2)

    try:
        with open(path, encoding="utf-8") as f:
            entries = _json.load(f)
    except Exception:
        entries = []

    by_label = {e["label"]: e for e in entries}

    scraped_labels = set()
    auto_labels = set()
    for val, label in auto_opts:
        auto_labels.add(label)
        scraped_labels.add(label)
        if label in by_label:
            by_label[label]["schedule_value"] = val
            by_label[label]["available"] = True
        else:
            by_label[label] = {"label": label, "schedule_value": val, "data_earn": None,
                               "available": True, "category": "Uncategorized"}

    for data_earn, label, is_trap in manual_opts:
        scraped_labels.add(label)
        if label in by_label:
            by_label[label]["data_earn"] = data_earn
            if is_trap and label not in auto_labels:
                by_label[label]["available"] = False
        else:
            by_label[label] = {"label": label, "schedule_value": None, "data_earn": data_earn,
                               "available": not is_trap, "category": "Uncategorized"}

    for label, entry in by_label.items():
        if entry.get("available") is True and label not in auto_labels:
            entry["available"] = False
        entry["enabled"] = label in scraped_labels

    with open(path, "w", encoding="utf-8") as f:
        _json.dump(list(by_label.values()), f, indent=2)


def handle_check_hospital_cases(action: Action, state: GameState):
    tasks = action.params.get("tasks", [])
    # Build priority-ordered list of enabled task types (skip target=none)
    # DNA processing requires home city — skip it when travelling
    in_home = state.in_home_city()
    priority = [
        t["type"] for t in tasks
        if t.get("target", "all") != "none" and t.get("enabled", True) is not False
        and not (t["type"] == "dna" and not in_home)
    ]

    _nav(_u("/localcity/hospital.asp?display=patients"), state)

    if not _check_session(state):
        return

    soup = BeautifulSoup(browser.page().content(), "html.parser")
    table = soup.find("table", attrs={"border": "1"})
    if not table:
        return

    # Parse each patient row: extract injury text and surgery/dna link
    available = {}  # task_type -> (label, url)
    rows = table.find_all("tr")
    for row in rows:
        cells = row.find_all("td", class_="display_border")
        if len(cells) < 2:
            continue
        patient_name = cells[0].get_text(strip=True)
        if state.own_name and patient_name.lower() == state.own_name.lower():
            continue
        patient_name = cells[0].get_text(strip=True)
        if state.own_name and patient_name.lower() == state.own_name.lower():
            continue
        injury = cells[1].get_text(strip=True)
        task_type = _hospital_injury_to_type(injury)
        link = row.find("a", href=lambda h: h and ("display=surgery" in h or "display=dna" in h))
        if link and task_type not in available:
            href = link["href"]
            if not href.startswith("http"):
                href = _u("/localcity/") + href
            available[task_type] = (injury, href)

    # Check for a separate DNA table — look for any heading containing "DNA"
    # followed by a table. Workflow is unknown; log and snapshot for investigation.
    page_html = browser.page().content()
    dna_soup = BeautifulSoup(page_html, "html.parser")
    dna_heading = dna_soup.find(lambda tag: tag.name in ("h2", "h3", "b", "strong", "p")
                                and "dna" in tag.get_text(strip=True).lower())
    if dna_heading:
        dna_table = dna_heading.find_next("table")
        if dna_table:
            dna_rows = [r for r in dna_table.find_all("tr")
                        if r.find_all("td", class_="display_border")]
            if dna_rows:
                state.add_log(f"Hospital: found {len(dna_rows)} DNA sample(s) — snapshotting for investigation.")
                _save_casework_snapshot("dna_samples", page_html)

    if not available:
        return

    # Pick first match in priority order; fall back to first available if no config
    chosen = None
    if priority:
        for task_type in priority:
            if task_type in available:
                chosen = available[task_type]
                break
    if not chosen:
        chosen = next(iter(available.values()))

    label, url = chosen
    state.add_log(f"Hospital case work: {label}.")
    _nav(url, state)

    soup = BeautifulSoup(browser.page().content(), "html.parser")
    success = soup.find("div", id="success")
    fail = soup.find("div", id="fail")
    if success:
        state.add_log(f"Hospital case work result: {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Hospital case work failed: {fail.get_text(strip=True)}")
    else:
        state.add_log("Hospital case work: submitted.")
    _refresh_state(state)


def handle_check_fire_cases(action: Action, state: GameState):
    page = browser.page()

    # Step 1 — active fires
    _nav(_u("/localcity/firestation.asp?display=fires"), state)
    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    table = soup.find("table", style=lambda s: s and "90%" in s)
    attend_links = []
    if table:
        for row in table.find_all("tr"):
            link = row.find("a", href=lambda h: h and "FightFire" in h)
            if link:
                href = link["href"]
                if not href.startswith("http"):
                    href = _u("/localcity/") + href
                victim_td = row.find("td", class_="display_border")
                victim = victim_td.get_text(strip=True) if victim_td else "?"
                attend_links.append((victim, href))

    if attend_links:
        victim, url = attend_links[-1]
        state.add_log(f"Fire case work: attending fire for {victim}.")
        _nav(url, state)
        result_soup = BeautifulSoup(page.content(), "html.parser")
        success = result_soup.find("div", id="success")
        fail    = result_soup.find("div", id="fail")
        if success:
            state.add_log(f"Fire case work result: {success.get_text(strip=True)}")
        elif fail:
            state.add_log(f"Fire case work failed: {fail.get_text(strip=True)}")
        else:
            state.add_log("Fire case work: submitted (no result div).")
        _refresh_state(state)

    # Step 2 — inspections (only if case timer is still free)
    if not state.timer_ready("case"):
        return

    _nav(_u("/localcity/firestation.asp?display=inspections"), state)
    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    table = soup.find("table", style=lambda s: s and "90%" in s)
    inspect_link = None
    if table:
        for row in table.find_all("tr"):
            link = row.find("a", href=lambda h: h and "inspect" in h)
            if link:
                href = link["href"]  # BeautifulSoup already decodes &amp; → &
                if not href.startswith("http"):
                    href = _u("/localcity/") + href.lstrip("/")
                inspect_link = href
                break

    if inspect_link:
        state.add_log("Fire case work: performing inspection.")
        _nav(inspect_link, state)
        result_soup = BeautifulSoup(page.content(), "html.parser")
        success = result_soup.find("div", id="success")
        fail    = result_soup.find("div", id="fail")
        if success:
            state.add_log(f"Fire inspection result: {success.get_text(strip=True)}")
        elif fail:
            state.add_log(f"Fire inspection failed: {fail.get_text(strip=True)}")
        else:
            state.add_log("Fire inspection: submitted (no result div).")
        _refresh_state(state)

    # Step 3 — investigations requested by police officers (only if case timer free).
    # These are listed on the same display=fires page as active fires.
    if not state.timer_ready("case"):
        return

    _nav(_u("/localcity/firestation.asp?display=fires"), state)
    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    investigate_links = []
    for link in soup.find_all("a", href=lambda h: h and "display=investigate&id=" in h):
        href = link["href"]  # BeautifulSoup already decodes &amp; → &
        if not href.startswith("http"):
            href = _u("/localcity/") + href.lstrip("/")
        investigate_links.append(href)

    if not investigate_links:
        return

    target = investigate_links[-1]  # last requested investigation
    state.add_log("Fire case work: performing investigation.")
    _nav(target, state)
    result_soup = BeautifulSoup(page.content(), "html.parser")
    success = result_soup.find("div", id="success")
    fail    = result_soup.find("div", id="fail")
    if success:
        state.add_log(f"Fire investigation result: {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Fire investigation failed: {fail.get_text(strip=True)}")
    else:
        state.add_log("Fire investigation: submitted (no result div).")
    _refresh_state(state)


def handle_clear_jail_duty_queue(action: Action, state: GameState):
    page = browser.page()
    _nav(_u("/jail/duties.asp"), state)

    if not _check_session(state):
        return

    _ensure_auto_earn_mode(page)

    btn = page.query_selector("button.mm-earn-queue-clear-btn")
    if not btn:
        state.add_log("Clear jail duty queue button not found.")
        return

    btn.click()
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log("Jail duty queue cleared.")

    duty = cfg.load().get("jail", {}).get("duty", "laundry")
    if duty in ("workshop", "kitchen", "laundry"):
        handle_jail_duties(Action("jail_duties", duty=duty), state)


# Jail-duty fallback order (highest tier → lowest). If the selected duty isn't
# available, step down from its position to the first available option
# (e.g. Workshop → Kitchen → Laundry).
_JAIL_DUTY_ORDER = ["digtunnel", "makeshank", "workshop", "kitchen", "laundry"]


def _pick_jail_duty(duty: str, available: list) -> "str | None":
    if duty in available:
        return duty
    if duty in _JAIL_DUTY_ORDER:
        for d in _JAIL_DUTY_ORDER[_JAIL_DUTY_ORDER.index(duty):]:
            if d in available:
                return d
    return available[-1] if available else None


def _handle_jail_duty_manual(duty: str, state: GameState):
    """Make Shank / Dig a tunnel are on the manual jail-duty form
    (/jail/duties.asp). If the auto queue is active (manual panel hidden), clear
    the queue and toggle to manual first, then submit one Work."""
    page = browser.page()
    _nav(_u("/jail/duties.asp"), state)
    if not _check_session(state):
        return

    # If auto form is visible (queue active), clear it first.
    try:
        page.wait_for_selector("div.mm-earn-mode-auto", timeout=5000)
    except Exception:
        pass
    auto_div = page.query_selector("div.mm-earn-mode-auto")
    if auto_div:
        auto_style = auto_div.get_attribute("style") or ""
        if "display: none" not in auto_style and "display:none" not in auto_style:
            handle_clear_jail_duty_queue(Action("clear_jail_duty_queue"), state)
            _nav(_u("/jail/duties.asp"), state)
            if not _check_session(state):
                return

    try:
        page.wait_for_selector("div.mm-earn-mode-manual", timeout=5000)
    except Exception:
        state.add_log("Jail duties: manual panel not found.")
        return
    manual = page.query_selector("div.mm-earn-mode-manual")
    if manual is None:
        state.add_log("Jail duties: manual panel not found.")
        return

    style = manual.get_attribute("style") or ""
    if "display: none" in style or "display:none" in style:
        # Toggle to manual mode.
        knob = page.query_selector("span.mm-earn-toggle-knob")
        if knob:
            knob.click()
            try:
                page.wait_for_function(
                    "() => { const el = document.querySelector('div.mm-earn-mode-manual'); "
                    "return el && !el.style.display.includes('none'); }",
                    timeout=5000,
                )
            except Exception:
                pass
            state.add_log("Jail duties: switched to MANUAL mode.")

    radio = page.query_selector(f"input[name='job'][value='{duty}']")
    if not radio:
        state.add_log(f"Jail duties: '{duty}' option not found.")
        return
    radio.check()
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    label = {"makeshank": "Make Shank", "digtunnel": "Dig a tunnel"}.get(duty, duty)
    soup = BeautifulSoup(page.content(), "html.parser")
    success = soup.find("div", id="success")
    fail    = soup.find("div", id="fail")
    if success:
        state.add_log(f"Jail duty ({label}): {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Jail duty ({label}) failed: {fail.get_text(strip=True)}")
    else:
        state.add_log(f"Jail duty ({label}): submitted.")


def handle_jail_duties(action: Action, state: GameState):
    duty = action.params["duty"]
    if duty in ("makeshank", "digtunnel"):
        _handle_jail_duty_manual(duty, state)
        return

    page = browser.page()
    _nav(_u("/jail/duties.asp"), state)

    if not _check_session(state):
        return

    _ensure_auto_earn_mode(page)

    soup = BeautifulSoup(page.content(), "html.parser")
    auto_panel = soup.find("div", class_="mm-earn-mode-auto")
    available_values = []
    if auto_panel:
        sel = auto_panel.find("select", attrs={"name": "schedule_earn_identifier"})
        if sel:
            available_values = [o.get("value", "") for o in sel.find_all("option")]

    chosen = _pick_jail_duty(duty, available_values)
    if not chosen:
        state.add_log("Jail duties: no duty options available on page.")
        return
    if chosen != duty:
        state.add_log(f"Jail duties: '{duty}' unavailable — stepping down to '{chosen}'.")

    cap_span = soup.find("span", class_="mm-earn-queue-cap")
    current_count = 0
    if cap_span:
        try:
            current_count = int(cap_span.get_text(strip=True).split("/")[0].strip())
        except (ValueError, IndexError):
            pass

    if current_count >= 50:
        state.add_log(f"Jail duty queue at {current_count}/200, no top-up needed.")
        return

    top_up = 200 - current_count
    state.add_log(f"Jail duty queue at {current_count}/200, topping up by {top_up} ({chosen}).")
    page.select_option("select[name='schedule_earn_identifier']", chosen)
    page.fill("input[name='schedule_count']", str(top_up))
    page.click("button.mm-earn-add-btn")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log("Jail duty queue topped up.")


def handle_jail_action(action: Action, state: GameState):
    jail_action = action.params["action"]
    page = browser.page()
    _nav(_u("/jail/contraband.asp"), state)

    if not _check_session(state):
        return

    # If the selected action isn't available, fall back to gym workout.
    order = [jail_action] + [a for a in ("gym",) if a != jail_action]
    chosen = next((a for a in order
                   if page.query_selector(f"input[type='radio'][value='{a}']")), None)
    if not chosen:
        state.add_log(f"Jail action: no radio available (wanted '{jail_action}').")
        return
    if chosen != jail_action:
        state.add_log(f"Jail action: '{jail_action}' unavailable — falling back to '{chosen}'.")
    jail_action = chosen

    page.check(f"input[type='radio'][value='{jail_action}']")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    soup = BeautifulSoup(browser.page().content(), "html.parser")
    success = soup.find("div", id="success")
    fail = soup.find("div", id="fail")
    if success:
        state.add_log(f"Jail action ({jail_action}): {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Jail action ({jail_action}) failed: {fail.get_text(strip=True)}")
    else:
        state.add_log(f"Jail action ({jail_action}): submitted.")


_JAIL_CONSUME_PRIORITY = ["porn", "booze", "cigarettes"]


def handle_jail_consume(action: Action, state: GameState):
    page = browser.page()
    _nav(_u("/jail/contraband.asp"), state)

    if not _check_session(state):
        return

    # Auto-pick highest-priority consumable the character actually has
    jcons = state.jail_consumables or {}
    consumable = next((c for c in _JAIL_CONSUME_PRIORITY if jcons.get(c, 0) > 0), None)
    if not consumable:
        state.add_log("Jail consume: no suitable consumables available.")
        return

    radio_value = _JAIL_RADIO_VALUE.get(consumable, consumable)
    radio = page.query_selector(f"input[type='radio'][value='{radio_value}']")
    if not radio:
        state.add_log(f"Jail consume: radio for '{consumable}' ({radio_value}) not found on page.")
        return

    page.check(f"input[type='radio'][value='{radio_value}']")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    soup = BeautifulSoup(browser.page().content(), "html.parser")
    success = soup.find("div", id="success")
    fail = soup.find("div", id="fail")
    name = JAIL_CONSUMABLE_NAMES.get(consumable, consumable.title())
    if success:
        state.add_log(f"Jail consume {name}: {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Jail consume {name} failed: {fail.get_text(strip=True)}")
    else:
        state.add_log(f"Jail consume {name}: submitted.")


def handle_deposit(action: Action, state: GameState):
    min_cash = int(action.params.get("min_cash_on_hand", 0))
    amount = (state.clean_money or 0) - min_cash
    if amount <= 0:
        state.add_log(f"Deposit: nothing to deposit (clean money {state.clean_money}, min {min_cash}).")
        return
    DEPOSIT_URL = _u("/income/bank.asp?option=deposit")
    page = browser.page()
    page.goto(DEPOSIT_URL, wait_until="domcontentloaded", timeout=15000)
    page.fill("input[name='deposit']", str(amount))
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded", timeout=10000)
    _refresh_state(state)
    state.add_log(f"Deposit: deposited ${amount:,}.")


def handle_bank_invest(action: Action, state: GameState):
    import re
    from datetime import datetime
    from tasks.banking import save_mature_date, load_mature_date
    import config as cfg

    bank_cfg = cfg.load().get("banking", {})
    term = bank_cfg.get("investment_term", "3,2.25")
    raw_amount = str(bank_cfg.get("invest_amount", 0))
    amount = int(re.sub(r"[^0-9]", "", raw_amount) or "0")
    if amount < 1:
        state.add_log("Banking: invest amount must be at least $1.")
        return
    amount = min(amount, 1500000)

    INVEST_URL = _u("/income/bank.asp?option=invest")
    page = browser.page()
    page.goto(INVEST_URL, wait_until="domcontentloaded", timeout=15000)

    soup = BeautifulSoup(page.content(), "html.parser")
    mature_td = None
    for td in soup.find_all("td"):
        strong = td.find("strong")
        if strong and "Mature Date" in strong.get_text():
            mature_td = td
            break
    if mature_td:
        raw_text = mature_td.get_text(separator=" ", strip=True)
        date_text = raw_text.replace("Mature Date:", "").strip()
        if date_text and date_text != "N/A":
            try:
                mature_dt = datetime.strptime(date_text, "%m/%d/%Y %I:%M:%S %p")
                mature_ts = mature_dt.timestamp()
                server_now = state._estimated_server_time()
                if server_now and mature_dt > server_now:
                    save_mature_date(mature_ts)
                    state.add_log(f"Banking: investment still active, matures at {date_text}.")
                    return
            except ValueError:
                pass

    page.select_option("select[name='terms']", term)
    page.fill("input[name='amount']", str(amount))
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded", timeout=10000)

    page.goto(INVEST_URL, wait_until="domcontentloaded", timeout=15000)
    soup = BeautifulSoup(page.content(), "html.parser")
    for td in soup.find_all("td"):
        strong = td.find("strong")
        if strong and "Mature Date" in strong.get_text():
            raw_text = td.get_text(separator=" ", strip=True)
            date_text = raw_text.replace("Mature Date:", "").strip()
            if date_text and date_text != "N/A":
                try:
                    mature_dt = datetime.strptime(date_text, "%m/%d/%Y %I:%M:%S %p")
                    save_mature_date(mature_dt.timestamp())
                    state.add_log(f"Banking: invested ${amount:,} at term {term}, matures at {date_text}.")
                except ValueError:
                    state.add_log(f"Banking: invested ${amount:,} at term {term}.")
                return
    state.add_log(f"Banking: invested ${amount:,} at term {term}.")


def _stash_held_weapon(state: GameState, label: str) -> bool:
    """Navigate to profile, check home city + apartment, then stash weapon in slot #1."""
    page = browser.page()
    if not state.in_home_city():
        state.add_log(f"{label}: not in home city — skipping stash, stopping loop.")
        return False
    _nav(_u("/profile/default.asp"), state)
    profile_soup = BeautifulSoup(page.content(), "html.parser")
    apt_found = False
    for tbl in profile_soup.select("#holder_content > table.item_table"):
        for row in tbl.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2 and cells[-2].get_text(strip=True).rstrip(":") == "Apartment":
                apt_found = True
                break
        if apt_found:
            break
    if not apt_found:
        state.add_log(f"{label}: no apartment on profile — skipping stash, stopping loop.")
        return False
    stash_link = page.query_selector("a[href='/weapons.asp?action=stash1']")
    if not stash_link:
        state.add_log(f"{label}: stash #1 link not found — stopping.")
        return False
    stash_link.click()
    page.wait_for_load_state("domcontentloaded")
    stash_soup = BeautifulSoup(page.content(), "html.parser")
    if stash_soup.find("div", id="fail"):
        state.add_log(f"{label}: stash failed — stopping.")
        return False
    state.add_log(f"{label}: stashed in slot #1.")
    return True


def handle_check_bionics(action: Action, state: GameState):
    from tasks.bionics import BIONIC_PRICES, REVERSE_ORDER
    import config as cfg
    wanted = cfg.load().get("bionics", {}).get("wanted_items", [])
    task = action.params.get("_task")

    if not wanted:
        state.add_log("Bionics: no wanted items configured.")
        return

    # Items to consider — use configured priority_order if set, else default REVERSE_ORDER
    priority_cfg = cfg.load().get("bionics", {}).get("priority_order", [])
    if priority_cfg:
        ordered_wanted = [i for i in priority_cfg if i in wanted]
    else:
        ordered_wanted = [i for i in REVERSE_ORDER if i in wanted]
    page = browser.page()

    def _parse_store() -> dict:
        soup = BeautifulSoup(page.content(), "html.parser")
        items = {}
        for row in soup.select("table tr"):
            radio = row.find("input", {"name": "bionic", "type": "radio"})
            if not radio:
                continue
            item_val = radio.get("value", "")
            tds = row.find_all("td")
            if len(tds) < 4:
                continue
            stock_text = tds[3].get_text(strip=True)
            try:
                stock = int(stock_text)
            except ValueError:
                continue
            items[item_val] = {"price": BIONIC_PRICES.get(item_val, 0), "stock": stock}
        if task is not None:
            views_p = soup.find("p", class_="center")
            if views_p:
                vm = re.search(r"Current Views:\s*(\d+)\s*/\s*(\d+)", views_p.get_text())
                if vm:
                    task.last_views = (int(vm.group(1)), int(vm.group(2)))
        return items

    def _nav_to_store():
        _nav(_u("/localcity/bionics.asp"), state)

    def _withdraw_for(price: int):
        if state.clean_money < price:
            needed = min(price - state.clean_money, state.bank_balance)
            if needed > 0:
                state.add_log(f"Bionics: withdrawing ${needed:,}.")
                handle_withdraw(Action("withdraw", amount=needed), state)

    def _in_stock_affordable():
        return [i for i in ordered_wanted
                if store.get(i, {}).get("stock", 0) > 0
                and BIONIC_PRICES[i] <= state.clean_money + state.bank_balance]

    # Step 4: Pre-withdraw for most expensive wanted item using fixed prices
    max_wanted_price = max((BIONIC_PRICES[i] for i in ordered_wanted), default=0)
    _withdraw_for(max_wanted_price)

    # Step 5: Navigate to store
    _nav_to_store()
    if not _check_session(state):
        return

    # Step 6: Parse store, record last_checked
    store = _parse_store()
    if task is not None:
        from tasks.bionics import save_bionics_state
        prev_ingame = task.last_checked_ingame
        task.last_checked_at = time.time()
        state_updates = {"last_checked_at": task.last_checked_at}

        # Restock detection — compare stock counts against last snapshot
        b = cfg.load().get("bionics", {})
        if b.get("auto_restock", False) and task.last_stock:
            restocked = [
                item for item, d in store.items()
                if d.get("stock", 0) > task.last_stock.get(item, 0)
            ]
            if restocked and state.ingame_mins is not None:
                igm        = state.ingame_mins
                start_mins = (igm + _window_start_offset(prev_ingame, igm)) % (24 * 60)
                end_mins   = (igm + 13 * 60 + 30) % (24 * 60)
                new_start  = f"{start_mins // 60:02d}:{start_mins % 60:02d}"
                new_end    = f"{end_mins   // 60:02d}:{end_mins   % 60:02d}"
                c = cfg.load()
                c["bionics"]["use_time_window"] = True
                c["bionics"]["window_start"]    = new_start
                c["bionics"]["window_end"]      = new_end
                cfg.save(c)
                import settings_rev; settings_rev.bump()
                msg = (f"Bionics restock detected ({', '.join(restocked)}) — "
                       f"buy window set to {new_start}–{new_end} in-game.")
                state.add_log(msg)
                _notify(state, "bionics_restock", msg)

        # Update last_stock snapshot
        task.last_stock = {item: d.get("stock", 0) for item, d in store.items()}
        state_updates["last_stock"] = task.last_stock
        if state.ingame_mins is not None:
            task.last_checked_ingame = state.ingame_mins
            state_updates["last_checked_ingame"] = state.ingame_mins
        save_bionics_state(state_updates)

    # Log anything currently in stock, regardless of whether the user wants it
    all_in_stock = [i for i, d in store.items() if d.get("stock", 0) > 0]
    if all_in_stock:
        msg = f"Bionics: in stock — {', '.join(all_in_stock)}."
        state.add_log(msg)
        _notify(state, "bionics_in_stock", msg)

    # Step 7: Filter wanted items in stock (reverse order)
    can_buy = _in_stock_affordable()
    if not [i for i in ordered_wanted if store.get(i, {}).get("stock", 0) > 0]:
        state.add_log("Bionics: no wanted items in stock.")
        return

    # Step 8: Affordability
    if not can_buy:
        in_stock = [i for i in ordered_wanted if store.get(i, {}).get("stock", 0) > 0]
        state.add_log(f"Bionics: in stock but cannot afford — {', '.join(f'{i} ${BIONIC_PRICES[i]:,}' for i in in_stock)}.")
        return

    # Step 9: Purchase loop
    purchased = []
    while can_buy:
        target = can_buy[0]
        price = BIONIC_PRICES[target]
        state.add_log(f"Bionics: purchasing {target} for ${price:,}.")
        page.check(f"input[name='bionic'][value='{target}']")
        page.click("input[type='submit'][name='B1'][value='Purchase']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)

        result_soup = BeautifulSoup(page.content(), "html.parser")
        success_div = result_soup.find("div", id="success")
        fail_div    = result_soup.find("div", id="fail")

        if success_div:
            msg = f"Bionics: purchased {target} — {success_div.get_text(strip=True)}"
            state.add_log(msg)
            _notify(state, "bionics_purchased", msg)
            purchased.append(target)
            store[target] = {"price": price, "stock": 0}
        elif fail_div:
            state.add_log(f"Bionics: purchase failed — {fail_div.get_text(strip=True)}")
            break
        else:
            state.add_log("Bionics: unexpected page after purchase — aborting.")
            break

        can_buy = _in_stock_affordable()
        if not can_buy:
            break

        # Stash before next purchase (guarded: home city + apartment required)
        if not _stash_held_weapon(state, "Bionics"):
            break

        # Withdraw for next item, then wait 30s, then navigate back
        next_price = BIONIC_PRICES[can_buy[0]]
        _withdraw_for(next_price)
        state.add_log("Bionics: waiting 30s before next purchase.")
        time.sleep(30)

        _nav_to_store()
        if not _check_session(state):
            break
        store = _parse_store()
        can_buy = _in_stock_affordable()

    if purchased:
        state.add_log(f"Bionics session complete — purchased: {', '.join(purchased)}.")


def handle_check_weapon_store(action: Action, state: GameState):
    import config as cfg
    ws_cfg = cfg.load().get("weapon_store", {})
    wanted = ws_cfg.get("wanted_items", [])
    task = action.params.get("_task")

    if not wanted:
        state.add_log("Weapon Store: no wanted items configured.")
        return

    page = browser.page()

    def _parse_store() -> dict:
        soup = BeautifulSoup(page.content(), "html.parser")
        items = {}
        for row in soup.select("table tr"):
            radio = row.find("input", {"name": "weapon", "type": "radio"})
            if not radio:
                continue
            item_val = radio.get("value", "")
            tds = row.find_all("td")
            if len(tds) < 4:
                continue
            price_text = tds[2].get_text(strip=True)
            stock_text = tds[3].get_text(strip=True)
            try:
                price = int(re.sub(r"[^0-9]", "", price_text) or 0)
                stock = int(stock_text)
            except ValueError:
                continue
            items[item_val] = {"price": price, "stock": stock}
        return items

    def _nav_to_store():
        _nav(_u("/localcity/weaponshop.asp"), state)

    def _withdraw_for(price: int):
        if state.clean_money < price:
            needed = min(price - state.clean_money, state.bank_balance)
            if needed > 0:
                state.add_log(f"Weapon Store: withdrawing ${needed:,}.")
                handle_withdraw(Action("withdraw", amount=needed), state)

    def _in_stock_affordable():
        return [i for i in ordered_wanted
                if store.get(i, {}).get("stock", 0) > 0
                and store.get(i, {}).get("price", 0) <= state.clean_money + state.bank_balance]

    # Build ordered_wanted from priority_order config, falling back to wanted order
    priority_cfg = ws_cfg.get("priority_order", [])
    if priority_cfg:
        ordered_wanted = [i for i in priority_cfg if i in wanted]
    else:
        ordered_wanted = list(wanted)

    # Pre-withdraw for the most expensive wanted item (using current store prices requires
    # visiting first, so we make a best-effort with whatever cash we have and withdraw later)
    _nav_to_store()
    if not _check_session(state):
        return

    store = _parse_store()
    if task is not None:
        from tasks.weapon_store import save_weapon_store_state
        prev_ingame = task.last_checked_ingame
        task.last_checked_at = time.time()
        state_updates = {"last_checked_at": task.last_checked_at}

        # Restock detection
        ws = cfg.load().get("weapon_store", {})
        if ws.get("auto_restock", False) and task.last_stock:
            restocked = [
                item for item, d in store.items()
                if d.get("stock", 0) > task.last_stock.get(item, 0)
            ]
            if restocked and state.ingame_mins is not None:
                igm        = state.ingame_mins
                start_mins = (igm + _window_start_offset(prev_ingame, igm)) % (24 * 60)
                end_mins   = (igm + 13 * 60 + 30) % (24 * 60)
                new_start  = f"{start_mins // 60:02d}:{start_mins % 60:02d}"
                new_end    = f"{end_mins   // 60:02d}:{end_mins   % 60:02d}"
                c = cfg.load()
                c["weapon_store"]["use_time_window"] = True
                c["weapon_store"]["window_start"]    = new_start
                c["weapon_store"]["window_end"]      = new_end
                cfg.save(c)
                import settings_rev; settings_rev.bump()
                msg = (f"Weapon Store restock detected ({', '.join(restocked)}) — "
                       f"buy window set to {new_start}–{new_end} in-game.")
                state.add_log(msg)
                _notify(state, "weapon_store_restock", msg)

        if state.ingame_mins is not None:
            task.last_checked_ingame = state.ingame_mins
            state_updates["last_checked_ingame"] = state.ingame_mins
        task.last_stock = {item: d.get("stock", 0) for item, d in store.items()}
        state_updates["last_stock"] = task.last_stock
        save_weapon_store_state(state_updates)

    all_in_stock = [i for i, d in store.items() if d.get("stock", 0) > 0]
    if all_in_stock:
        msg = f"Weapon Store: in stock — {', '.join(all_in_stock)}."
        state.add_log(msg)
        _notify(state, "weapon_store_in_stock", msg)

    can_buy = _in_stock_affordable()
    if not [i for i in ordered_wanted if store.get(i, {}).get("stock", 0) > 0]:
        state.add_log("Weapon Store: no wanted items in stock.")
        return

    if not can_buy:
        in_stock = [i for i in ordered_wanted if store.get(i, {}).get("stock", 0) > 0]
        parts = [f"{i} ${store[i]['price']:,}" for i in in_stock]
        state.add_log(f"Weapon Store: in stock but cannot afford — {', '.join(parts)}.")
        return

    # Purchase loop
    purchased = []
    while can_buy:
        target = can_buy[0]
        price = store[target]["price"]
        _withdraw_for(price)
        state.add_log(f"Weapon Store: purchasing {target} for ${price:,}.")
        page.check(f"input[name='weapon'][value='{target}']")
        page.click("input[type='submit'][name='B1'][value='Purchase']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)

        result_soup = BeautifulSoup(page.content(), "html.parser")
        success_div = result_soup.find("div", id="success")
        fail_div    = result_soup.find("div", id="fail")

        if success_div:
            msg = f"Weapon Store: purchased {target} — {success_div.get_text(strip=True)}"
            state.add_log(msg)
            _notify(state, "weapon_store_purchased", msg)
            purchased.append(target)
            store[target] = {"price": price, "stock": 0}
        elif fail_div:
            state.add_log(f"Weapon Store: purchase failed — {fail_div.get_text(strip=True)}")
            break
        else:
            state.add_log("Weapon Store: unexpected page after purchase — aborting.")
            break

        can_buy = _in_stock_affordable()
        if not can_buy:
            break

        # Stash before next purchase (guarded: home city + apartment required)
        if not _stash_held_weapon(state, "Weapon Store"):
            break

        # Withdraw for next item, wait 30s, navigate back
        next_price = store[can_buy[0]]["price"]
        _withdraw_for(next_price)
        state.add_log("Weapon Store: waiting 30s before next purchase.")
        time.sleep(30)

        _nav_to_store()
        if not _check_session(state):
            break
        store = _parse_store()
        can_buy = _in_stock_affordable()

    if purchased:
        state.add_log(f"Weapon Store session complete — purchased: {', '.join(purchased)}.")


DRUG_STORE_PRICES = {"Pseudoephedrine": 500, "Epipen": 25_000, "Medipack": 1_000_000}


def handle_check_drug_store(action: Action, state: GameState):
    import config as cfg
    ds_cfg = cfg.load().get("drug_store", {})
    wanted = ds_cfg.get("wanted_items", [])
    task = action.params.get("_task")

    if not wanted:
        state.add_log("Drug Store: no wanted items configured.")
        return

    priority_cfg = ds_cfg.get("priority_order", [])
    if priority_cfg:
        ordered_wanted = [i for i in priority_cfg if i in wanted]
    else:
        ordered_wanted = list(wanted)

    page = browser.page()

    def _parse_store() -> dict:
        soup = BeautifulSoup(page.content(), "html.parser")
        items = {}
        for row in soup.select("table tr"):
            radio = row.find("input", {"name": "product", "type": "radio"})
            if not radio:
                continue
            item_val = radio.get("value", "")
            tds = row.find_all("td")
            if len(tds) < 4:
                continue
            stock_text = tds[3].get_text(strip=True)
            try:
                stock = int(stock_text)
            except ValueError:
                continue
            items[item_val] = {"stock": stock, "price": DRUG_STORE_PRICES.get(item_val, 0)}
        return items

    most_expensive = max(DRUG_STORE_PRICES.get(i, 0) for i in ordered_wanted)
    if state.clean_money < most_expensive:
        needed = most_expensive - state.clean_money
        state.add_log(f"Drug Store: withdrawing ${needed:,}.")
        handle_withdraw(Action("withdraw", amount=needed), state)

    _nav(_u("/localcity/drugstore.asp"), state)
    if not _check_session(state):
        return

    store = _parse_store()

    if task is not None:
        from tasks.drug_store import save_drug_store_state
        # Restock detection
        if task.last_stock:
            restocked = [
                item for item, d in store.items()
                if d.get("stock", 0) > task.last_stock.get(item, 0)
            ]
            if restocked:
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                c = cfg.load()
                c.setdefault("drug_store", {})["last_restock_at"] = now_str
                cfg.save(c)
                import settings_rev; settings_rev.bump()
                msg = (f"Drug Store restock detected ({', '.join(restocked)}) at {now_str}.")
                state.add_log(msg)
                _notify(state, "drug_store_restock", msg)

        task.last_checked_at = time.time()
        task.last_stock = {item: d.get("stock", 0) for item, d in store.items()}
        save_drug_store_state({
            "last_checked_at": task.last_checked_at,
            "last_stock": task.last_stock,
        })

    def _in_stock_affordable():
        return [i for i in ordered_wanted
                if store.get(i, {}).get("stock", 0) > 0
                and DRUG_STORE_PRICES.get(i, 0) <= state.clean_money + state.bank_balance]

    can_buy = _in_stock_affordable()
    if not can_buy:
        return

    for _attempt in range(3):
        target = can_buy[0]
        price = DRUG_STORE_PRICES.get(target, 0)
        state.add_log(f"Drug Store: purchasing {target} for ${price:,}.")
        page.check(f"input[name='product'][value='{target}']")
        page.click("input[type='submit'][name='B1'][value='Purchase']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)

        result_soup = BeautifulSoup(page.content(), "html.parser")
        success_div = result_soup.find("div", id="success")
        fail_div = result_soup.find("div", id="fail")

        if success_div:
            msg = f"Drug Store: purchased {target} — {success_div.get_text(strip=True)}"
            state.add_log(msg)
            _notify(state, "drug_store_purchased", msg)
            if task is not None:
                task.purchase_cooldown_until = time.time() + 1800
                save_drug_store_state({"purchase_cooldown_until": task.purchase_cooldown_until})
            return
        elif fail_div:
            state.add_log(f"Drug Store: purchase failed — {fail_div.get_text(strip=True)}, retrying.")
            _nav(_u("/localcity/drugstore.asp"), state)
            if not _check_session(state):
                return
            store = _parse_store()
            can_buy = _in_stock_affordable()
            if not can_buy:
                return
        else:
            state.add_log("Drug Store: unexpected page after purchase — aborting.")
            return


def handle_withdraw(action: Action, state: GameState):
    amount = int(action.params.get("amount", 0))
    if amount <= 0:
        state.add_log("Withdraw: amount must be greater than zero.")
        return
    WITHDRAW_URL = _u("/income/bank.asp?option=withdrawal")
    page = browser.page()
    page.goto(WITHDRAW_URL, wait_until="domcontentloaded", timeout=15000)
    page.fill("input[name='withdrawal']", str(amount))
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded", timeout=10000)
    _refresh_state(state)
    state.add_log(f"Withdraw: withdrew ${amount:,}.")


# ---------------------------------------------------------------------------
# Executor
def _jailbreak_result(soup) -> str:
    """Extract the result message from a jailbreak.asp response page.

    The result sits inside the right-hand td.s1 as one or more <p> tags.
    """
    td = soup.find("td", class_="s1")
    if td:
        parts = [p.get_text(" ", strip=True) for p in td.find_all("p") if p.get_text(strip=True)]
        if parts:
            return " ".join(parts)
    return ""


def handle_jailbreak_plan(action: Action, state: GameState):
    target = action.params.get("target", "")
    partner = action.params.get("partner", "")
    hold = action.params.get("hold_action_timer", False)

    # A partner is required to plan a jail break.
    if not (partner or "").strip():
        state.add_log("Jail break plan: no partner set — skipping.")
        return

    # Only gangsters can plan a jail break away from their home city.
    if "gangster" not in (state.occupation or "").lower() and not state.in_home_city():
        state.add_log("Jail break plan: non-gangster cannot plan outside home city — skipping.")
        return

    page = browser.page()
    page.goto(_u("/income/jailbreak.asp"), wait_until="domcontentloaded", timeout=15000)
    url = browser.current_url()

    if "jailbreak.asp" not in url:
        soup = BeautifulSoup(page.content(), "html.parser")
        msg = _jailbreak_result(soup) or url
        state.add_log(f"Jail break plan failed: {msg}")
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    select = soup.find("select", attrs={"name": "jailbreak"})
    if not select:
        state.add_log("Jail break plan: form not found on page.")
        return

    option_values = [o.get("value", "") for o in select.find_all("option") if o.get("value")]

    if "execute" in option_values or "calloff" in option_values:
        state.add_log("Jail break plan failed: a jail break is already planned — execute or call off first.")
        return

    if "plannew" not in option_values:
        state.add_log("Jail break plan: 'Plan a new jail break' option not available.")
        return

    page.select_option("select[name='jailbreak']", "plannew")
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded", timeout=10000)

    # Fill target and partner on the planning form
    page.fill("input[name='escaper']", target)
    page.fill("input[name='partner']", partner)
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded", timeout=10000)

    soup = BeautifulSoup(page.content(), "html.parser")
    msg = _jailbreak_result(soup)
    state.add_log(f"Jail break planned (target: {target}, partner: {partner}): {msg or 'submitted.'}")
    state.hold_action_timer = hold
    _refresh_state(state)


def handle_jailbreak_execute(action: Action, state: GameState):
    page = browser.page()
    page.goto(_u("/income/jailbreak.asp"), wait_until="domcontentloaded", timeout=15000)
    url = browser.current_url()

    if "jailbreak.asp" not in url:
        soup = BeautifulSoup(page.content(), "html.parser")
        msg = _jailbreak_result(soup) or url
        state.add_log(f"Jail break execute failed: {msg}")
        state.hold_action_timer = False
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    select = soup.find("select", attrs={"name": "jailbreak"})
    if not select:
        state.add_log("Jail break execute: form not found.")
        state.hold_action_timer = False
        return

    option_values = [o.get("value", "") for o in select.find_all("option") if o.get("value")]
    if "execute" not in option_values:
        state.add_log("Jail break execute: no jail break planned to execute.")
        state.hold_action_timer = False
        return

    page.select_option("select[name='jailbreak']", "execute")
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded", timeout=10000)

    soup = BeautifulSoup(page.content(), "html.parser")
    msg = _jailbreak_result(soup)
    state.add_log(f"Jail break executed: {msg or 'submitted.'}")
    state.hold_action_timer = False
    _refresh_state(state)


def handle_jailbreak_calloff(action: Action, state: GameState):
    page = browser.page()
    page.goto(_u("/income/jailbreak.asp"), wait_until="domcontentloaded", timeout=15000)
    url = browser.current_url()

    if "jailbreak.asp" not in url:
        soup = BeautifulSoup(page.content(), "html.parser")
        msg = _jailbreak_result(soup) or url
        state.add_log(f"Jail break call off failed: {msg}")
        state.hold_action_timer = False
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    select = soup.find("select", attrs={"name": "jailbreak"})
    if not select:
        state.add_log("Jail break call off: form not found.")
        state.hold_action_timer = False
        return

    option_values = [o.get("value", "") for o in select.find_all("option") if o.get("value")]
    if "calloff" not in option_values:
        state.add_log("Jail break call off: no jail break to call off.")
        state.hold_action_timer = False
        return

    page.select_option("select[name='jailbreak']", "calloff")
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded", timeout=10000)

    soup = BeautifulSoup(page.content(), "html.parser")
    msg = _jailbreak_result(soup)
    state.add_log(f"Jail break called off: {msg or 'submitted.'}")
    state.hold_action_timer = False
    _refresh_state(state)


# ---------------------------------------------------------------------------
# Drug trade handler
# ---------------------------------------------------------------------------

def handle_check_drug_trade(action: Action, state: GameState):
    import config as cfg
    c = cfg.load()
    autobuy = c.get("autobuy", {})
    if not autobuy.get("enabled", False):
        return

    drug_cfg = autobuy.get("drugs", {})

    _nav(_u("/income/drugtrade.asp"), state)
    if not _check_session(state):
        return

    soup = BeautifulSoup(state.page_html, "html.parser")

    # Collect offer IDs from the list page
    offer_ids = []
    for a in soup.find_all("a", class_="viewbutton_small"):
        href = a.get("href", "")
        m = re.search(r"offerid=(\d+)", href)
        if m:
            offer_ids.append(m.group(1))

    if not offer_ids:
        state.add_log("Drug trade: no offers found.")
        return

    state.add_log(f"Drug trade: found {len(offer_ids)} offer(s).")

    for offer_id in offer_ids:
        offer_url = _u("/income/drugtrade.asp") + f"?display=offer&offerid={offer_id}"
        _nav(offer_url, state)
        if not _check_session(state):
            return

        soup = BeautifulSoup(state.page_html, "html.parser")

        # Parse price
        price_tag = soup.find("font", attrs={"size": "5"})
        if not price_tag:
            state.add_log(f"Drug trade offer {offer_id}: price not found, skipping.")
            continue
        try:
            offer_price = int(re.sub(r"[^0-9]", "", price_tag.get_text()))
        except ValueError:
            state.add_log(f"Drug trade offer {offer_id}: could not parse price, skipping.")
            continue

        # Parse items — all item_info tds share one <tr>, all item_content tds share the next.
        # Pair them by index to get the right qty for each drug.
        items = []
        info_tds = soup.find_all("td", class_="item_info")
        content_tds = soup.find_all("td", class_="item_content")
        for i, item_td in enumerate(info_tds):
            for img in item_td.find_all("img"):
                img.decompose()
            raw_name = item_td.get_text(strip=True).lower()
            drug_key = _DRUG_TRADE_NAME_MAP.get(raw_name)
            qty = 0
            if i < len(content_tds):
                try:
                    qty = int(re.sub(r"[^0-9]", "", content_tds[i].get_text()))
                except ValueError:
                    pass
            items.append((raw_name, drug_key, qty))

        if not items:
            state.add_log(f"Drug trade offer {offer_id}: no items parsed, skipping.")
            continue

        # Compute total willing-to-pay across all items in this offer
        total_willing = 0
        decline_reasons = []
        for raw_name, drug_key, qty in items:
            if drug_key is None:
                state.add_log(f"Drug trade offer {offer_id}: unknown drug '{raw_name}' — treating as $0.")
                decline_reasons.append(f"unknown drug '{raw_name}'")
                continue

            dcfg = drug_cfg.get(drug_key, {})
            max_price = dcfg.get("max_price", 0)
            max_qty = dcfg.get("max_qty", 0)
            held = state.consumables.get(drug_key, 0)

            if max_qty == 0:
                decline_reasons.append(f"{drug_key} max_qty=0")
                # willing stays $0
            elif held >= max_qty:
                decline_reasons.append(f"{drug_key} held {held}>={max_qty}")
                # willing stays $0
            else:
                total_willing += max_price * qty

        item_summary = ", ".join(
            f"{qty}x {raw_name}" for raw_name, _, qty in items
        )
        state.add_log(
            f"Drug trade offer {offer_id} [{item_summary}] "
            f"price=${offer_price:,} willing=${total_willing:,}"
        )

        if total_willing < offer_price:
            reason = "; ".join(decline_reasons) if decline_reasons else "price too high"
            state.add_log(f"Drug trade offer {offer_id}: not accepting ({reason}).")
            continue

        # Funding check — use dirty money; if short, withdraw clean money from bank
        if state.dirty_money < offer_price:
            needed = offer_price - state.dirty_money - state.clean_money
            withdraw_amount = max(needed, 0)
            if withdraw_amount > 0:
                state.add_log(
                    f"Drug trade: dirty money short (${state.dirty_money:,}), "
                    f"withdrawing ${withdraw_amount:,} from bank."
                )
                handle_withdraw(Action("withdraw", amount=withdraw_amount), state)
            if state.dirty_money + state.clean_money < offer_price:
                state.add_log(
                    f"Drug trade offer {offer_id}: insufficient funds after withdrawal "
                    f"(have dirty=${state.dirty_money:,} clean=${state.clean_money:,}, "
                    f"need=${offer_price:,}) — skipping offer."
                )
                continue

        # Accept
        accept_url = _u("/income/drugtrade.asp") + f"?action=accept&offerid={offer_id}"
        _nav(accept_url, state)
        state.add_log(f"Drug trade offer {offer_id}: accepted [{item_summary}] for ${offer_price:,}.")


# ---------------------------------------------------------------------------
# Blind eye handler
# ---------------------------------------------------------------------------

def handle_blind_eye(action: Action, state: GameState):
    import config as cfg
    q = cfg.blind_eye_queue_peek()
    if not q:
        state.add_log("Blind eye: queue is empty.")
        return

    _nav(_u("/income/blindeye.asp"), state)
    if not _check_session(state):
        return
    soup = BeautifulSoup(state.page_html, "html.parser")
    select = soup.find("select", attrs={"name": "gangster"})
    if not select:
        for name in list(q):
            cfg.blind_eye_queue_remove(name)
        state.add_log("Blind eye: no gangster selector found on page, queue cleared.")
        return

    options = {opt.get_text(strip=True): opt.get("value", "")
               for opt in select.find_all("option") if opt.get("value", "Please") != "Please"}

    for name in list(q):
        if name in options:
            page = browser.page()
            page.select_option("select[name='gangster']", options[name])
            page.click("input[type='submit'][name='B1']")
            page.wait_for_load_state("domcontentloaded")
            _refresh_state(state)
            result_soup = BeautifulSoup(state.page_html, "html.parser")
            success = result_soup.find("div", id="success")
            fail = result_soup.find("div", id="fail")
            if success:
                state.add_log(f"Blind eye ({name}): {success.get_text(strip=True)}")
            elif fail:
                state.add_log(f"Blind eye ({name}): {fail.get_text(strip=True)}")
            else:
                text = result_soup.get_text(" ", strip=True)[:200]
                state.add_log(f"Blind eye ({name}): {text}")
            cfg.blind_eye_queue_remove(name)
            return

        cfg.blind_eye_queue_remove(name)
        state.add_log(f"Blind eye ({name}): not found in selector, removed from queue.")

    state.add_log("Blind eye: no queued names matched the selector.")


# ---------------------------------------------------------------------------
# Journal handlers
# ---------------------------------------------------------------------------

def _extract_action_urls_from_soup(soup, entry_id):
    """Find accept/decline URLs for a journal entry by its ID."""
    accept_url = decline_url = ""
    label = soup.find("label", attrs={"for": entry_id})
    if not label:
        return accept_url, decline_url
    row = label.find_parent("tr")
    if not row:
        return accept_url, decline_url
    sibling = row.find_next_sibling("tr")
    if not sibling:
        return accept_url, decline_url
    for a in sibling.find_all("a", href=True):
        href = a["href"]
        if "actionevent.asp" not in href:
            continue
        if "action=accept" in href:
            accept_url = href
        elif "action=decline" in href:
            decline_url = href
    return accept_url, decline_url


def handle_check_journals(action: Action, state: GameState):
    from tasks.journal import (
        _load_journals, _save_journals, _parse_journal_rows,
        _new_entries_on_page, _is_last_page, _next_page_url,
        dispatch_journal_action,
    )
    char = state.own_name
    if not char:
        return

    data = _load_journals(char)
    url = _u("/journal/journal.asp")
    changed = False

    while True:
        _nav(url, state)
        soup = BeautifulSoup(state.page_html, "html.parser")

        new_entries = _new_entries_on_page(soup)
        all_entries = _parse_journal_rows(soup)

        for e in new_entries:
            if e["id"] not in data:
                e["type"] = "events"
                data[e["id"]] = e
                changed = True
                dispatch_journal_action(e, state)

        all_new = len(new_entries) == len(all_entries) and len(all_entries) > 0
        last = _is_last_page(soup)

        if all_new and not last:
            next_url = _next_page_url(soup)
            if next_url:
                url = next_url
                continue

        # Backfill non-new entries on this final page
        for e in all_entries:
            if e["id"] not in data:
                e["type"] = "events"
                data[e["id"]] = e
                changed = True
        break

    if changed:
        _save_journals(char, data)
        state.journals_updated_at = time.time()

    # Always check the requests page — the journal indicator doesn't reliably
    # distinguish events from requests, and the count badge may not appear.
    _nav(_u("/journal/journal.asp?display=requests"), state)
    req_soup = BeautifulSoup(state.page_html, "html.parser")
    req_entries = _parse_journal_rows(req_soup)
    live_ids = {e["id"] for e in req_entries}

    for e in req_entries:
        if e["id"] not in data:
            e["type"] = "requests"
            accept_url, decline_url = _extract_action_urls_from_soup(req_soup, e["id"])
            if accept_url:
                e["accept_url"] = accept_url
            if decline_url:
                e["decline_url"] = decline_url
            data[e["id"]] = e
            changed = True
            dispatch_journal_action(e, state)
        elif data[e["id"]].get("status") == "inactive":
            data[e["id"]].pop("status", None)
            changed = True

    for eid, entry in data.items():
        if entry.get("type") == "requests" and entry.get("status") != "inactive" and eid not in live_ids:
            entry["status"] = "inactive"
            changed = True

    if changed:
        _save_journals(char, data)
        state.journals_updated_at = time.time()
        state.add_log(f"Journals: {len(req_entries)} active request(s) found — checked requests page.")

    state.has_new_journals = False


def handle_archive_journals(action: Action, state: GameState):
    from tasks.journal import (
        _load_journals, _save_journals, _parse_journal_rows,
        _is_last_page, _next_page_url,
    )
    char = state.own_name
    if not char:
        return

    max_pages = action.params.get("pages")  # None = archive all
    data = _load_journals(char)
    url = _u("/journal/journal.asp")
    page_num = 1
    changed = False

    while True:
        _nav(url, state)
        soup = BeautifulSoup(state.page_html, "html.parser")

        for e in _parse_journal_rows(soup):
            if e["id"] not in data:
                data[e["id"]] = e
                changed = True

        if _is_last_page(soup):
            break
        if max_pages is not None and page_num >= max_pages:
            break

        next_url = _next_page_url(soup)
        if not next_url:
            break
        url = next_url
        page_num += 1

    if changed:
        _save_journals(char, data)
        state.journals_updated_at = time.time()


def handle_journal_action(action: Action, state: GameState):
    action_url = action.params.get("url", "")
    entry_id = action.params.get("entry_id", "")
    action_type = action.params.get("action_type", "")
    if not action_url:
        state.add_log("Journal action: no URL provided.")
        return
    if action_url.startswith("http"):
        full = action_url
    elif action_url.startswith("/"):
        full = _u(action_url)
    else:
        full = _u("/journals/" + action_url)
    _nav(full, state)
    if not _check_session(state):
        return
    soup = BeautifulSoup(state.page_html, "html.parser")
    success = soup.find("div", id="success")
    fail = soup.find("div", id="fail")
    if success:
        state.add_log(f"Journal {action_type} (#{entry_id}): {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Journal {action_type} (#{entry_id}): {fail.get_text(strip=True)}")
    else:
        text = soup.get_text(" ", strip=True)[:200]
        state.add_log(f"Journal {action_type} (#{entry_id}): {text}")


# ---------------------------------------------------------------------------
# Warrant handlers
# ---------------------------------------------------------------------------

def handle_check_warrants(action: Action, state: GameState):
    result_queue = action.params.get("result_queue")
    _nav(_u("/localcity/warrants.asp"), state)
    if not _check_session(state):
        if result_queue is not None:
            result_queue.put([])
        return

    soup = BeautifulSoup(state.page_html, "html.parser")
    table = soup.find("table", class_="mm-list-table")
    warrants = []
    if table:
        for row in table.find_all("tr"):
            cells = row.find_all("td", class_="display_border")
            if len(cells) < 6:
                continue
            turn_in_a = row.find("a", class_="box")
            href = turn_in_a["href"] if turn_in_a else ""
            if href and not href.startswith("http"):
                href = urls.BASE_URL + href
            warrants.append({
                "case_id":   cells[0].get_text(strip=True),
                "crime":     cells[1].get_text(strip=True),
                "victim":    cells[2].get_text(strip=True),
                "fine":      cells[3].get_text(strip=True),
                "jail_time": cells[4].get_text(strip=True),
                "css":       cells[5].get_text(strip=True),
                "defense":   cells[6].get_text(strip=True) if len(cells) > 6 else "",
                "turn_in_url": href,
            })

    state.add_log(f"Warrants: found {len(warrants)} active warrant(s).")
    if result_queue is not None:
        result_queue.put(warrants)


def handle_turn_in_warrant(action: Action, state: GameState):
    url = action.params["url"]
    case_id = action.params.get("case_id", "")
    jail_time = action.params.get("jail_time", "")
    css = action.params.get("css", "")
    fine = action.params.get("fine", "")
    defense = action.params.get("defense", "")
    details = ", ".join(p for p in [
        f"jail: {jail_time}" if jail_time else "",
        f"CS: {css}" if css else "",
        f"fine: {fine}" if fine else "",
        f"defense: {defense}" if defense else "",
    ] if p)
    _nav(url, state)
    soup = BeautifulSoup(state.page_html, "html.parser")
    success = soup.find("div", id="success")
    fail = soup.find("div", id="fail")
    detail_str = f" ({details})" if details else ""
    if success:
        state.add_log(f"Warrant {case_id}{detail_str}: turned in — {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Warrant {case_id}{detail_str}: failed — {fail.get_text(strip=True)}")
    else:
        state.add_log(f"Warrant {case_id}{detail_str}: submitted.")


# ---------------------------------------------------------------------------
# Illness handler
# ---------------------------------------------------------------------------

def handle_apply_illness_treatment(action: Action, state: GameState):
    _nav(_u("/localcity/hospital.asp?display=apply"), state)
    if not _check_session(state):
        return
    page = browser.page()
    soup = BeautifulSoup(page.content(), "html.parser")
    sel = soup.find("select", {"name": "display"})
    if not sel:
        state.add_log("Illness: treatment form not found — may already be on waiting list or no illness present.")
        return
    page.select_option("select[name='display']", "Yes")
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded", timeout=10000)
    _refresh_state(state)
    soup2 = BeautifulSoup(page.content(), "html.parser")
    content = soup2.get_text(" ", strip=True)
    if "waiting list" in content.lower() or "applied" in content.lower() or "treatment" in content.lower():
        state.add_log("Illness: successfully applied for flu treatment.")
    else:
        state.add_log("Illness: submitted form but could not confirm result.")


# ---------------------------------------------------------------------------
# Travel / vehicle handlers
# ---------------------------------------------------------------------------

_GYM_URL = "/localcity/businesses.asp?name=Gym"
_TRAVEL_URL = "/travel/travel.asp"
_REPAIRS_URL = "/localcity/repairs.asp"
_DEPART_URL = "/travel/depart.asp"
_AIRPORT_URL = "/travel/airport.asp"
_CHICAGO = "Chicago"
_NO_VEHICLE_TEXT = "you don't own a vehicle, it's parked or it's stashed in your vehicles vault"

_pending_vehicle_travel_target: str = ""


def get_pending_vehicle_travel_target() -> str:
    return _pending_vehicle_travel_target


def clear_pending_vehicle_travel_target():
    global _pending_vehicle_travel_target
    _pending_vehicle_travel_target = ""


# Deferred travel: a manual travel requested while the travel timer wasn't free.
_deferred_travel: "dict | None" = None


def get_deferred_travel() -> "dict | None":
    return _deferred_travel


def clear_deferred_travel():
    global _deferred_travel
    _deferred_travel = None

_CASINO_URL = "/localcity/businesses.asp?name=Casino"
_BEIRUT = "Beirut"
_CASINO_STOP_TEXT = "don't you think"
_CASINO_RADIO_VALUE = {"slots": "slot", "blackjack": "blackjack"}

_CARD_RANK_VALUE = {
    "a": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
    "10": 10, "t": 10, "j": 10, "q": 10, "k": 10,
}


def _card_rank_value(img_src: str) -> "int | None":
    """Parse a card image filename like 'js.gif' or '10c.gif' into a blackjack rank value."""
    m = re.search(r"/([0-9]{1,2}|[ajqkt])([cdhs])\.gif", img_src, re.I)
    if not m:
        return None
    return _CARD_RANK_VALUE.get(m.group(1).lower())


def handle_check_vehicle(action: Action, state: GameState) -> int:
    _nav(_u(_REPAIRS_URL), state)
    if not _check_session(state):
        return 0
    if "/localcity/local.asp" in browser.current_url():
        state.add_log("Check vehicle: repairs unavailable (local.asp redirect).")
        state.vehicle_health = None
        return -1  # distinct from 0 so travel can proceed anyway
    soup = BeautifulSoup(state.page_html, "html.parser")
    if _NO_VEHICLE_TEXT in state.page_html.lower():
        state.add_log("Check vehicle: no vehicle available.")
        state.vehicle_health = None
        return 0
    # Game shows this div when vehicle is at full health and needs no repairs
    no_repairs = soup.find("div", id="fail")
    if no_repairs and "doesn't need any repairs" in no_repairs.get_text():
        state.vehicle_health = 100
        state.add_log("Check vehicle: health 100% (no repairs needed).")
        return 100
    bar = soup.find("div", id="respect_bar")
    if not bar:
        state.add_log("Check vehicle: could not find health bar.")
        state.vehicle_health = None
        return 0
    m = re.search(r"(\d+)", bar.get_text())
    pct = int(m.group(1)) if m else 0
    state.vehicle_health = pct
    state.add_log(f"Check vehicle: health {pct}%.")
    return pct


def handle_repair_vehicle(action: Action, state: GameState) -> bool:
    if _REPAIRS_URL not in (state.current_url or ""):
        _nav(_u(_REPAIRS_URL), state)
    if not _check_session(state):
        return False
    if "/localcity/local.asp" in browser.current_url():
        state.add_log("Repair vehicle: repairs unavailable (local.asp redirect).")
        return False
    if _NO_VEHICLE_TEXT in state.page_html.lower():
        state.add_log("Repair vehicle: no vehicle to repair.")
        return False
    soup = BeautifulSoup(state.page_html, "html.parser")
    # Check and withdraw funds if needed
    cost_font = soup.find("font", color="gold")
    if cost_font:
        cost_m = re.search(r"\$([\d,]+)", cost_font.get_text())
        if cost_m:
            cost = int(cost_m.group(1).replace(",", ""))
            if state.clean_money < cost:
                needed = cost - state.clean_money
                state.add_log(f"Repair vehicle: need ${cost:,}, withdrawing ${needed:,}.")
                handle_withdraw(Action("withdraw", amount=needed), state)
                if state.clean_money < cost:
                    state.add_log("Repair vehicle: insufficient funds — skipping.")
                    return False
    page = browser.page()
    page.select_option("select[name='display']", "Yes")
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    if _NO_VEHICLE_TEXT in state.page_html.lower():
        state.add_log("Repair vehicle: booking failed.")
        return False
    state.add_log("Repair vehicle: repair booked successfully.")
    return True


def handle_travel(action: Action, state: GameState) -> int:
    from datetime import datetime
    global _travel_warrant_cooldown_until
    target = action.params.get("target_city", "")
    method = action.params.get("method", "airport")

    if not target:
        state.add_log("Travel: no target city specified.")
        return 0

    if state.current_city.lower() == target.lower():
        state.add_log(f"Travel: already in {target}.")
        return 1

    # Pre-travel warrant check
    if time.monotonic() < _travel_warrant_cooldown_until:
        state.add_log("Travel: warrant cooldown active — skipping travel.")
        return 0

    warrant_mode = cfg.load().get("jail", {}).get("auto_warrant_handling", "none")
    result_q = queue.Queue()
    handle_check_warrants(Action("check_warrants", result_queue=result_q), state)
    try:
        warrants = result_q.get(timeout=10)
    except queue.Empty:
        warrants = []

    if warrants:
        def _jail_time_nonzero(s: str) -> bool:
            s = s.strip().lower()
            return bool(s) and s not in ("0", "—", "-", "none", "no jail", "")

        turned_in_ids = set()
        for w in warrants:
            defense = w.get("defense", "").strip().lower()
            jail_nz = _jail_time_nonzero(w.get("jail_time", ""))
            is_failed = defense == "failed"

            if defense not in ("failed", "no"):
                if defense:
                    state.add_log(
                        f"Warrant {w['case_id']}: unexpected defense value "
                        f"'{w['defense']}' — skipping."
                    )
                continue

            should_turn_in = (
                warrant_mode == "all"
                or (warrant_mode == "failed_no_jail"   and is_failed and not jail_nz)
                or (warrant_mode == "failed_incl_jail" and is_failed)
            )

            if should_turn_in:
                handle_turn_in_warrant(
                    Action("turn_in_warrant", url=w["turn_in_url"], case_id=w["case_id"],
                           jail_time=w.get("jail_time", ""), css=w.get("css", ""),
                           fine=w.get("fine", ""), defense=w.get("defense", "")),
                    state,
                )
                turned_in_ids.add(w["case_id"])

        remaining = [w for w in warrants if w["case_id"] not in turned_in_ids]
        if remaining:
            ids = ", ".join(w["case_id"] for w in remaining)
            msg = (f"Travel: {len(remaining)} outstanding warrant(s) ({ids}) — "
                   f"aborting travel for 1 hour.")
            state.add_log(msg)
            _travel_warrant_cooldown_until = time.monotonic() + 3600
            _notify(state, "warrants_outstanding", msg)
            return 0

    # If the travel timer isn't free, defer this travel until it is (state is
    # fresh from the warrant-check navigation above). A missing timer entry means
    # travel is available (the game only shows the timer while on cooldown).
    if "travel" in state.timers and not state.timer_ready("travel"):
        global _deferred_travel
        _deferred_travel = {"target_city": target, "method": method}
        state.add_log(f"Travel: travel timer not ready — travel to {target} deferred until it's free.")
        return 0

    if method == "own_vehicle":
        pct = handle_check_vehicle(Action("check_vehicle"), state)
        if pct == -1:
            # Repairs page redirected to local.asp — attempt travel anyway.
            state.add_log("Travel: repairs page unavailable (local redirect) — attempting travel anyway.")
        elif state.vehicle_health is None:
            return 0
        elif pct == 0:
            ok = handle_repair_vehicle(Action("repair_vehicle"), state)
            if ok:
                global _pending_vehicle_travel_target
                _pending_vehicle_travel_target = target
                state.add_log(f"Travel: vehicle sent for repair — travel to {target} deferred until repair complete.")
                return 1
            return 0

        # Navigate to travel.asp and parse available destinations
        _nav(_u(_TRAVEL_URL), state)
        if not _check_session(state):
            return 0
        soup = BeautifulSoup(state.page_html, "html.parser")
        dest_map = {}
        for div in soup.find_all("div", class_="city-container"):
            inner = div.find("div", class_="city-travel-container")
            if not inner:
                continue
            city_name = inner.get("id", "")
            link = inner.find("a", href=re.compile(r"depart\.asp\?destination="))
            if city_name and link:
                dest_map[city_name.lower()] = link["href"]
        match_href = dest_map.get(target.lower())
        if not match_href:
            state.add_log(f"Travel: {target} not available on travel.asp.")
            return 0
        url = _u(match_href) if match_href.startswith("/") else urls.BASE_URL + "/travel/" + match_href
        _nav(url, state)
        if not _check_session(state):
            return 0
        soup = BeautifulSoup(state.page_html, "html.parser")
        breakdown = soup.find(lambda tag: tag.name and "out of the blue, your" in tag.get_text(strip=True).lower())
        if breakdown:
            state.add_log(f"Travel: vehicle broke down en route to {target} — booking repair.")
            ok = handle_repair_vehicle(Action("repair_vehicle"), state)
            if ok:
                _pending_vehicle_travel_target = target
                state.add_log(f"Travel: repair booked — travel to {target} deferred until repair complete.")
                return 1
            return 0
        state.add_log(f"Travel: departing to {target} by vehicle.")
        # After travelling, re-check the vehicle and book a repair if it broke down.
        post_pct = handle_check_vehicle(Action("check_vehicle"), state)
        if state.vehicle_health is not None and post_pct == 0:
            state.add_log("Travel: vehicle broken down after travel — booking repair.")
            handle_repair_vehicle(Action("repair_vehicle"), state)
        return 1

    # Airport method
    _nav(_u(_AIRPORT_URL), state)
    if not _check_session(state):
        return 0
    if "local.asp" in browser.current_url():
        state.add_log(f"Travel: airport not available (redirected to local).")
        return 0

    soup = BeautifulSoup(state.page_html, "html.parser")

    # Check if already booked
    for td in soup.find_all("td"):
        if state.own_name and state.own_name.lower() in td.get_text(strip=True).lower():
            state.add_log(f"Travel: flight already booked.")
            _set_flight_timer(soup, state)
            return 1

    dest_select = soup.find("select", attrs={"name": "destination"})
    if not dest_select:
        state.add_log("Travel: could not find destination selector.")
        return 0

    available = {o.get("value", ""): o for o in dest_select.find_all("option") if o.get("value") and o.get("value") != "0"}
    match = next((v for v in available if v.lower() == target.lower()), None)
    if not match:
        state.add_log(f"Travel: {target} not available in airport dropdown.")
        return 0

    minutes = available[match].get("data-minutes", "?")
    page = browser.page()
    page.select_option("select[name='destination']", match)
    page.click("input[name='action']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    _set_flight_timer(soup, state)
    state.add_log(f"Travel: flight to {target} booked ({minutes} min travel time).")
    return 1


def _set_flight_timer(soup, state: GameState):
    """Parse data-date-end from the airport timer div and store in state."""
    from state import SERVER_TIME_FMT
    import time as _time
    timer_div = soup.find(attrs={"data-date-end": True, "data-text-end": True})
    if not timer_div:
        return
    end_str = timer_div.get("data-date-end", "").strip()
    try:
        from datetime import datetime
        end_dt = datetime.strptime(end_str, SERVER_TIME_FMT)
        if state.server_time:
            delta = (end_dt - state.server_time).total_seconds()
            state.flight_departs_at = _time.time() + delta
    except (ValueError, TypeError):
        pass


# ---------------------------------------------------------------------------
# Gym handler
# ---------------------------------------------------------------------------


def handle_gym(action: Action, state: GameState):
    import config as cfg
    import time
    from tasks.gym import save_last_gym_use

    gym_cfg = cfg.load().get("gym", {})
    activity = gym_cfg.get("activity", "weights")
    auto_travel = gym_cfg.get("auto_travel", False)

    # Travel to Chicago if needed
    if state.current_city != _CHICAGO:
        if not auto_travel:
            state.add_log("Gym: not in Chicago and auto-travel is off — skipping.")
            return
        global _gym_travel_cooldown_until
        state.add_log("Gym: travelling to Chicago...")
        method = "own_vehicle"
        result = handle_travel(Action("travel", target_city=_CHICAGO, method=method), state)
        if result == 0:
            _gym_travel_cooldown_until = time.monotonic() + 3600
            state.add_log("Gym: travel to Chicago failed — skipping gym for 1 hour.")
            return
        if state.current_city != _CHICAGO:
            _gym_travel_cooldown_until = time.monotonic() + 3600
            state.add_log(f"Gym: still not in Chicago after travel ({state.current_city}) — skipping gym for 1 hour.")
            return

    # Navigate to gym page
    _nav(_u(_GYM_URL), state)
    if not _check_session(state):
        return

    soup = BeautifulSoup(state.page_html, "html.parser")

    # Check if membership purchase form is shown
    membership_form = soup.find("select", attrs={"name": "option"})
    if membership_form and any(
        o.get("value") == "purchase" for o in membership_form.find_all("option")
    ):
        # Parse cost
        cost = 0
        cost_p = soup.find("p", string=re.compile(r"current cost", re.I))
        if cost_p:
            m = re.search(r"\$([\d,]+)", cost_p.get_text())
            if m:
                cost = int(m.group(1).replace(",", ""))

        if cost > 0 and state.clean_money < cost:
            needed = cost - state.clean_money
            state.add_log(f"Gym: need ${cost:,} for membership, have ${state.clean_money:,} — withdrawing ${needed:,}.")
            handle_withdraw(Action("withdraw", amount=needed), state)
            if state.clean_money < cost:
                state.add_log("Gym: still insufficient funds after withdrawal — skipping.")
                return

        # Purchase membership
        page = browser.page()
        page.select_option("select[name='option']", "purchase")
        page.click("input[type='submit'][name='B1']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)
        state.add_log(f"Gym: purchased membership (${cost:,}).")

        # Navigate back to gym activity page
        _nav(_u(_GYM_URL), state)
        if not _check_session(state):
            return
        soup = BeautifulSoup(state.page_html, "html.parser")

    # Do the activity
    activity_select = soup.find("select", attrs={"name": "option"})
    if not activity_select or not any(
        o.get("value") == activity for o in activity_select.find_all("option")
    ):
        state.add_log(f"Gym: activity '{activity}' not available on page.")
        return

    page = browser.page()
    page.select_option("select[name='option']", activity)
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    save_last_gym_use(time.time())
    state.add_log(f"Gym: completed activity '{activity}'.")


def _casino_stopped(soup: "BeautifulSoup") -> bool:
    fail_div = soup.find("div", id="fail")
    if fail_div and _CASINO_STOP_TEXT in fail_div.get_text(" ", strip=True).lower():
        return True
    return _CASINO_STOP_TEXT in soup.get_text(" ", strip=True).lower()


def _parse_casino_release(soup: "BeautifulSoup", state: GameState) -> "float | None":
    """Extract the 'Try again after <date>!' timestamp from the casino fail div, anchored to wall clock."""
    from state import SERVER_TIME_FMT
    from datetime import datetime
    fail_div = soup.find("div", id="fail")
    text = fail_div.get_text(" ", strip=True) if fail_div else soup.get_text(" ", strip=True)
    m = re.search(r"Try again after (.+?)!", text, re.I)
    if not m or not state.server_time:
        return None
    try:
        release_dt = datetime.strptime(m.group(1).strip(), SERVER_TIME_FMT)
    except (ValueError, TypeError):
        return None
    offset = (release_dt - state.server_time).total_seconds()
    return time.time() + offset


def _handle_casino_stop(soup: "BeautifulSoup", state: GameState, label: str):
    from tasks.casino import save_casino_release_at
    from datetime import datetime
    release_at = _parse_casino_release(soup, state)
    if release_at is not None:
        save_casino_release_at(release_at)
        state.add_log(f"{label}: session over, locked out until {datetime.fromtimestamp(release_at).strftime('%Y-%m-%d %H:%M:%S')}.")
    else:
        state.add_log(f"{label}: session over.")


def _play_slots(state: GameState, bet_amount: int):
    page = browser.page()
    bet = max(100, min(99999, bet_amount))
    while True:
        soup = BeautifulSoup(page.content(), "html.parser")
        if not soup.find("input", attrs={"name": "bet"}):
            if _casino_stopped(soup):
                _handle_casino_stop(soup, state, "Casino (Slots)")
            else:
                state.add_log("Casino (Slots): bet input not found — stopping.")
            return
        page.fill("input[name='bet']", str(bet))
        page.click("input[name='B1']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)
        if not _check_session(state):
            return

        result_soup = BeautifulSoup(page.content(), "html.parser")
        if _casino_stopped(result_soup):
            _handle_casino_stop(result_soup, state, "Casino (Slots)")
            return
        if not result_soup.find("input", attrs={"name": "bet"}):
            state.add_log("Casino (Slots): no further bet form — stopping.")
            return


def _play_blackjack_hand(state: GameState, bet_amount: int) -> bool:
    """Play a single hand to completion. Returns True if another hand can be started."""
    page = browser.page()
    bet = max(100, min(50000, bet_amount))

    soup = BeautifulSoup(page.content(), "html.parser")
    if not soup.find("input", attrs={"name": "bet"}):
        if _casino_stopped(soup):
            _handle_casino_stop(soup, state, "Casino (Blackjack)")
        else:
            state.add_log("Casino (Blackjack): bet input not found — stopping.")
        return False
    page.fill("input[name='bet']", str(bet))
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    if not _check_session(state):
        return False

    while True:
        soup = BeautifulSoup(page.content(), "html.parser")
        if _casino_stopped(soup):
            _handle_casino_stop(soup, state, "Casino (Blackjack)")
            return False

        total_match = re.search(r"Current Card total\s*=\s*(\d+)", soup.get_text(" "), re.I)
        result_buttons = soup.find_all("input", attrs={"name": "result"})
        if not total_match or not result_buttons:
            outcome = soup.find("font", attrs={"color": re.compile("red|green", re.I)})
            if outcome:
                state.add_log(f"Casino (Blackjack): {outcome.get_text(strip=True)}")
            else:
                state.add_log("Casino (Blackjack): hand resolved.")

            continue_btn = soup.find("input", attrs={"name": "B1", "value": re.compile("continue", re.I)})
            if continue_btn:
                page.click("input[name='B1'][value='Continue']")
                page.wait_for_load_state("domcontentloaded")
                _refresh_state(state)
                if not _check_session(state):
                    return False
                continue_soup = BeautifulSoup(page.content(), "html.parser")
                if _casino_stopped(continue_soup):
                    _handle_casino_stop(continue_soup, state, "Casino (Blackjack)")
                    return False
            return True

        player_total = int(total_match.group(1))
        dealer_card_value = None
        dealer_label = soup.find(string=re.compile(r"Blackjack Machines 1st card", re.I))
        if dealer_label:
            dealer_img = dealer_label.find_next("img")
            if dealer_img:
                dealer_card_value = _card_rank_value(dealer_img.get("src", ""))

        if player_total >= 17:
            action_value = "Stay"
        elif player_total <= 11:
            action_value = "Hit"
        else:
            dealer_strong = dealer_card_value is None or dealer_card_value >= 7
            action_value = "Hit" if dealer_strong else "Stay"

        if not any(b.get("value") == action_value for b in result_buttons):
            state.add_log(f"Casino (Blackjack): '{action_value}' button not available — stopping.")
            return False

        page.click(f"input[name='result'][value='{action_value}']")
        page.wait_for_load_state("domcontentloaded")
        _refresh_state(state)
        if not _check_session(state):
            return False


def handle_casino(action: Action, state: GameState):
    casino_cfg = cfg.load().get("casino", {})
    activity = casino_cfg.get("activity", "slots")
    bet_amount = int(casino_cfg.get("bet_amount", 100))
    auto_travel = casino_cfg.get("auto_travel", False)

    if state.current_city != _BEIRUT:
        if not auto_travel:
            return
        state.add_log("Casino: travelling to Beirut...")
        result = handle_travel(Action("travel", target_city=_BEIRUT, method="own_vehicle"), state)
        if result == 0:
            state.add_log("Casino: travel to Beirut failed — skipping.")
            return
        if state.current_city != _BEIRUT:
            state.add_log(f"Casino: still not in Beirut after travel ({state.current_city}) — skipping.")
            return

    _nav(_u(_CASINO_URL), state)
    if not _check_session(state):
        return

    page = browser.page()
    radio_value = _CASINO_RADIO_VALUE.get(activity, "slot")
    soup = BeautifulSoup(page.content(), "html.parser")
    if not soup.find("input", attrs={"name": "casinooption", "value": radio_value}):
        state.add_log(f"Casino: could not find the '{activity}' option on the casino page.")
        return
    page.check(f"input[name='casinooption'][value='{radio_value}']")
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    if not _check_session(state):
        return
    if "/localcity/local.asp" in browser.current_url():
        from tasks.casino import save_casino_release_at
        release_at = time.time() + 10 * 60
        save_casino_release_at(release_at)
        state.add_log("Casino: unavailable (redirected to local city) — retrying in 10 minutes.")
        return
    if not _check_session(state):
        return

    if activity == "blackjack":
        while _play_blackjack_hand(state, bet_amount):
            pass
    else:
        _play_slots(state, bet_amount)


_ENG_SECTION_KEYS = {
    "new building requests":    "construct_apartment",
    "business repairs":         "repair_business",
    "vehicle repair requests":  "repair_vehicle",
    "vault construction requests": "construct_vault",
}


def _click_eng_submit(page, radio_name: str, radio_value: str):
    """Click the first submit button that follows the given radio in DOM order."""
    with page.expect_navigation(wait_until="domcontentloaded"):
        page.evaluate(f"""() => {{
            const radio = document.querySelector(
                'input[type="radio"][name="{radio_name}"][value="{radio_value}"]'
            );
            if (!radio) return;
            const allEls = Array.from(document.querySelectorAll('*'));
            const radioIdx = allEls.indexOf(radio);
            const btn = allEls.slice(radioIdx + 1).find(
                el => el.tagName === 'INPUT' && el.type === 'submit'
            );
            if (btn) btn.click();
        }}""");


def _finish_eng(state: GameState):
    html = browser.page().content()
    _save_casework_snapshot("engineering_result", html)
    result_soup = BeautifulSoup(html, "html.parser")
    # The result div lives inside div#content but before div#shop_holder.
    # Search that outer region so section-level fail divs don't shadow it.
    pre_body = []
    content_div = result_soup.find("div", id="content")
    if content_div:
        for child in content_div.children:
            if hasattr(child, "get") and child.get("id") == "shop_holder":
                break
            pre_body.append(str(child))
    search_root = BeautifulSoup("".join(pre_body), "html.parser") if pre_body else result_soup
    # Collect all success/fail divs in document order and pick the topmost one
    all_divs = search_root.find_all("div")
    result_div = None
    is_success = False
    for div in all_divs:
        div_id = div.get("id", "")
        div_cls = set(div.get("class", []))
        if div_id == "success" or "success" in div_cls or div_cls >= {"info", "green"}:
            result_div = div
            is_success = True
            break
        if div_id == "fail" or "fail" in div_cls or div_cls >= {"info", "red"}:
            result_div = div
            is_success = False
            break
    if result_div:
        prefix = "Engineering result" if is_success else "Engineering failed"
        state.add_log(f"{prefix}: {result_div.get_text(strip=True)}")
    else:
        state.add_log("Engineering case work: submitted.")
    _refresh_state(state)


def handle_check_engineering_cases(action: Action, state: GameState):
    if not state.timers.get("case", {}).get("ready", True):
        return

    tasks = action.params.get("tasks", [])
    # Build priority list; repair_business uses enabled flag, others use target
    priority = []
    task_cfg = {}
    for t in tasks:
        typ = t["type"]
        if typ == "repair_business":
            if t.get("enabled", True) is not False:
                priority.append(typ)
            task_cfg[typ] = t
        else:
            if t.get("target", "all") != "none":
                priority.append(typ)
            task_cfg[typ] = t

    page = browser.page()
    _nav(_u("/income/construction.asp"), state)
    if not _check_session(state):
        return

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    _save_casework_snapshot("engineering", html)

    # Split page into sections by column_title divs
    sections = {}  # type_key -> list of tags between this title and the next
    current_key = None
    current_tags = []
    holder = soup.find("div", id="holder_content")
    children = holder.children if holder else soup.children
    for tag in children:
        if hasattr(tag, "get") and "column_title" in tag.get("class", []):
            if current_key:
                sections[current_key] = current_tags
            heading = tag.get_text(strip=True).lower()
            current_key = next((v for k, v in _ENG_SECTION_KEYS.items() if k in heading), None)
            current_tags = []
        elif current_key is not None:
            current_tags.append(tag)
    if current_key:
        sections[current_key] = current_tags

    def _section_soup(tags):
        combined = "".join(str(t) for t in tags)
        return BeautifulSoup(combined, "html.parser")

    def _target_ok(username, task_type):
        cfg = task_cfg.get(task_type, {})
        target = cfg.get("target", "all")
        if target == "all":
            return True
        if target == "whitelist":
            return username in (state.whitelist or [])
        if target == "not_blacklist":
            return username not in (state.blacklist or [])
        return False

    # Try each type in priority order
    for typ in priority:
        if typ not in sections:
            continue
        sec = _section_soup(sections[typ])

        if typ == "repair_business":
            radio = sec.find("input", {"type": "radio", "name": "Req_id"})
            if not radio:
                continue
            val = radio.get("value", "")
            state.add_log(f"Engineering: repair business job #{val}.")
            page.check(f"input[type='radio'][name='Req_id'][value='{val}']")
            _click_eng_submit(page, "Req_id", val)
            _finish_eng(state)
            return

        if typ == "construct_apartment":
            radios = sec.find_all("input", {"type": "radio", "name": "Req_username"})
            for radio in radios:
                username = radio.get("value", "")
                if state.own_name and username.lower() == state.own_name.lower():
                    continue
                if not _target_ok(username, typ):
                    continue
                state.add_log(f"Engineering: construct apartment for '{username}'.")
                page.check(f"input[type='radio'][name='Req_username'][value='{username}']")
                _click_eng_submit(page, "Req_username", username)
                _finish_eng(state)
                return
        else:
            radios = sec.find_all("input", {"type": "radio", "name": "Req_id"})
            for radio in radios:
                val = radio.get("value", "")
                # Try to find the requester username from nearby text
                parent = radio.parent
                username = ""
                if parent:
                    for sib in parent.find_all("td"):
                        txt = sib.get_text(strip=True)
                        if txt and not txt.isdigit() and txt != val:
                            username = txt
                            break
                if state.own_name and username.lower() == state.own_name.lower():
                    continue
                if username and not _target_ok(username, typ):
                    continue
                label = "repair vehicle" if typ == "repair_vehicle" else "construct vault"
                state.add_log(f"Engineering: {label} job #{val}" + (f" for '{username}'" if username else "") + ".")
                page.check(f"input[type='radio'][name='Req_id'][value='{val}']")
                _click_eng_submit(page, "Req_id", val)
                _finish_eng(state)
                return



def handle_fetch_respect(action: Action, state: GameState):
    from tasks.respect import save_respect_data
    import time as _time
    if not state.own_name:
        return
    page = browser.page()
    _nav(_u(f"/userprofile.asp?username={state.own_name}"), state)
    if not _check_session(state):
        return
    soup = BeautifulSoup(page.content(), "html.parser")
    bar = soup.find("div", id="respect_bar")
    if bar:
        pct = bar.get_text(strip=True)
        save_respect_data(pct, _time.time())
        state.add_log(f"Respect: {pct}")
    else:
        save_respect_data(None, _time.time())
    _nav(_u("/main.asp"), state)


def handle_fetch_profile(action: Action, state: GameState):
    result_q = action.params.get("result_queue")
    try:
        _nav(_u("/profile/default.asp"), state)
        soup = BeautifulSoup(browser.page().content(), "html.parser")
        result = {}

        info_table = soup.select_one("#account_profile table.item_table")
        if info_table:
            for row in info_table.find_all("tr"):
                cells = row.find_all("td")
                for i in range(0, len(cells) - 1, 2):
                    label = cells[i].get_text(strip=True).rstrip(":")
                    value = cells[i + 1].get_text(strip=True)
                    result[label] = value

        bionics = []
        for div in soup.select("#account_bionics [id^='player_bionic']"):
            a = div.find("a", class_="title")
            if a and a.get("title"):
                name = a["title"].split("|")[0].replace(" installed", "").strip()
                if name:
                    bionics.append(name)
        result["bionics"] = bionics

        weapons = []
        for tbl in soup.select(".showWeapons table.item_table"):
            w = {}
            slot_div = tbl.select_one("td[colspan] div")
            if slot_div:
                w["slot"] = slot_div.get_text(strip=True)
            item_td = tbl.find("td", class_="item_content")
            if item_td:
                w["item"] = item_td.get_text(strip=True)
            dur_div = tbl.select_one(".item_shots_content div")
            if dur_div:
                w["durability"] = dur_div.get_text(strip=True)
            actions = []
            action_td = tbl.select_one("td.item_content[align='center']")
            if action_td:
                for a in action_td.find_all("a"):
                    href = a.get("href", "")
                    label = a.get_text(strip=True)
                    if href and label:
                        actions.append({"label": label, "url": href})
            w["actions"] = actions
            if w:
                weapons.append(w)
        result["weapons"] = weapons

        apt = {}
        for tbl in soup.select("#holder_content > table.item_table"):
            for row in tbl.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[-2].get_text(strip=True).rstrip(":")
                    value = cells[-1].get_text(strip=True)
                    if label in ("Apartment", "Status", "Storage"):
                        apt[label] = value
            apt_link = tbl.select_one("td.item_content[colspan='3'] a")
            if apt_link:
                apt["action_url"] = apt_link.get("href", "")
                apt["action_label"] = apt_link.get_text(strip=True)
        if apt:
            result["apartment"] = apt

        vehicles = []
        for tbl in soup.select("#holder_content > table[cellspacing='2'].item_table"):
            v = {}
            for row in tbl.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[-2].get_text(strip=True).rstrip(":")
                    if label in ("Type", "Condition", "Location", "Parking/security"):
                        v[label] = cells[-1].get_text(strip=True)
                    elif label == "Action":
                        actions = []
                        for a in cells[-1].find_all("a"):
                            href = a.get("href", "")
                            lbl = a.get_text(strip=True)
                            if href and lbl:
                                actions.append({"label": lbl, "url": href})
                        v["actions"] = actions
            if v.get("Type"):
                vehicles.append(v)
        result["vehicles"] = vehicles

        pets = []
        for tbl in soup.select(".showPets table.item_table"):
            p = {}
            for row in tbl.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 2:
                    label = cells[0].get_text(strip=True).rstrip(":")
                    val = cells[-1].get_text(strip=True)
                    if label in ("Name", "Breed", "Age", "Fights won", "Fights lost"):
                        p[label] = val
            slot_div = tbl.select_one("td[colspan] div")
            if slot_div:
                p["slot"] = slot_div.get_text(strip=True)
            if p.get("Breed"):
                pets.append(p)
        result["pets"] = pets

        businesses = []
        for tbl in soup.select(".showBusinesses table.item_table"):
            for row in tbl.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    businesses.append({
                        "name": cells[0].get_text(strip=True),
                        "next_restock": cells[1].get_text(strip=True),
                    })
        result["businesses"] = businesses

        misc = []
        for tbl in soup.select("#holder_content > table.item_table"):
            for td in tbl.select("td.item_info"):
                text = td.get_text(strip=True)
                if " - " in text:
                    misc.append(text)
        result["misc"] = misc

        if result_q is not None:
            result_q.put(result)
    except Exception as e:
        if result_q is not None:
            result_q.put(e)
        raise


def handle_navigate(action: Action, state: GameState):
    url = action.params.get("url", "")
    if url:
        if url.startswith("/"):
            url = _u(url)
        _nav(url, state)


def _parse_event_consumables(soup, state: GameState):
    """Parse the #eventboss_collecteditems block into
    state.event_consumables = {name: {"qty": int, "url": str}}."""
    container = soup.find("div", id="eventboss_collecteditems")
    if not container:
        return
    items = {}
    for div in container.find_all("div", onclick=True):
        oc = div.get("onclick", "")
        tm = re.search(r"type=([A-Za-z0-9_]+)", oc)
        if not tm:
            continue
        name = tm.group(1)
        um = re.search(r"href='([^']+)'", oc)
        url = (um.group(1) if um else "").replace("&amp;", "&")
        qm = re.search(r"Collected:\s*(\d+)", div.get_text())
        qty = int(qm.group(1)) if qm else 0
        items[name] = {"qty": qty, "url": url}
    state.event_consumables = items


def handle_event_consume(action: Action, state: GameState):
    """Consume one event-boss item by following its consume URL."""
    name = action.params.get("name", "")
    url  = action.params.get("url", "")
    if not url:
        return
    if url.startswith("http"):
        full = url
    elif url.startswith("/"):
        full = _u(url)
    else:
        full = _u("/" + url)

    _nav(full, state)
    if not _check_session(state):
        return

    soup = BeautifulSoup(browser.page().content(), "html.parser")
    success = soup.find("div", id="success")
    fail    = soup.find("div", id="fail")
    if success:
        state.add_log(f"Event consume {name}: {success.get_text(strip=True)}")
        ec = (state.event_consumables or {}).get(name)
        if ec and ec.get("qty", 0) > 0:
            ec["qty"] -= 1  # keep local count accurate between bossevent visits
    elif fail:
        msg = fail.get_text(strip=True)
        state.add_log(f"Event consume {name} failed: {msg}")
        # Out of stock — zero it locally so we stop retrying until next visit.
        if any(p in msg.lower() for p in ("do not have", "don't have", "none left", "0x")):
            if name in (state.event_consumables or {}):
                state.event_consumables[name]["qty"] = 0
    else:
        state.add_log(f"Event consume {name}: submitted (no result div).")
    _refresh_state(state)


def _parse_whacks_survived(soup):
    """Whacks-survived count from a profile page, or None."""
    a = soup.find("a", id=re.compile(r"^award_survived"))
    if not a:
        return None
    m = re.search(r"(\d+)\s+survived whacks", a.get("title", ""))
    return int(m.group(1)) if m else None


def handle_ws_monitor(action: Action, state: GameState):
    """Sweep the War Mode watch lists, parsing whacks-survived from each
    profile. war_mode.record_ws stamps a whack + logs an event on an increase."""
    import war_mode
    if state.server_time is not None:
        war_mode.set_server_now(state.server_time)
    target = (action.params.get("target") or "").strip()
    pairs = war_mode.all_names()
    if target:
        pairs = [(s, n) for (s, n) in pairs if n.lower() == target.lower()]
    if not pairs:
        return
    checked = whacked = 0
    for side, name in pairs:
        try:
            _nav(_u(f"/userprofile.asp?username={name}"), state)
            if not _check_session(state):
                return
            soup = BeautifulSoup(browser.page().content(), "html.parser")
            ws = _parse_whacks_survived(soup)
            if ws is None:
                continue
            if war_mode.record_ws(name, side, ws):
                whacked += 1
            checked += 1
        except Exception as e:
            state.add_log(f"WS monitor: error checking {name}: {e}")
    msg = f"WS monitor: checked {checked} name(s)."
    if whacked:
        msg += f" {whacked} newly whacked."
    state.add_log(msg)


def handle_refresh_event_inventory(action: Action, state: GameState):
    """Visit bossevent.asp once to capture the current event-consumable stock
    (used on login so the inventory is known before any attack cycle)."""
    _nav(_u("/conflict/bossevent.asp"), state)
    if not _check_session(state):
        return
    soup = BeautifulSoup(browser.page().content(), "html.parser")
    _parse_event_consumables(soup, state)
    n = len(state.event_consumables or {})
    state.add_log(f"Event inventory refreshed: {n} item type(s) collected.")


def handle_event_boss(action: Action, state: GameState):
    """Attack the event boss on /conflict/bossevent.asp.

    Follows the ATTACK! link (id changes over time — matched on action=attack,
    not the exact URL) and logs the success/fail result. When no attack link is
    present the boss is assumed to be respawning; sets state._event_boss_hold so
    the task backs off for 5 minutes."""
    page = browser.page()
    _nav(_u("/conflict/bossevent.asp"), state)
    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    _parse_event_consumables(soup, state)

    attack_href = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "bossevent.asp" in href and "action=attack" in href:
            attack_href = href
            break

    if not attack_href:
        state._event_boss_hold = True
        state.add_log("Event Boss: no attack link — boss respawning, holding 5 min.")
        return

    if attack_href.startswith("http"):
        url = attack_href
    elif attack_href.startswith("/"):
        url = _u(attack_href)
    else:
        url = _u("/conflict/" + attack_href)

    _nav(url, state)
    if not _check_session(state):
        return

    result_soup = BeautifulSoup(page.content(), "html.parser")
    success = result_soup.find("div", id="success")
    fail    = result_soup.find("div", id="fail")
    if success:
        state.add_log(f"Event Boss attack: {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Event Boss attack: {fail.get_text(strip=True)}")
    else:
        state.add_log("Event Boss attack: no success/fail result parsed.")


def handle_launder_money(action: Action, state: GameState):
    global _launder_cooldown_until, _launder_cooldown_city
    page = browser.page()
    _nav(_u("/income/laundering.asp"), state)

    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    contacts = []
    for td in soup.find_all("td", class_="display_border"):
        link = td.find("a", href=lambda h: h and "laundering.asp?action=launder" in h)
        if link:
            href = link["href"]
            m = re.search(r"id=(\d+)", href)
            if m:
                contacts.append({"name": link.get_text(strip=True), "id": m.group(1)})

    if not contacts:
        _launder_cooldown_until = time.monotonic() + 1800
        _launder_cooldown_city = state.current_city
        state.add_log("Laundering: no contacts available — cooling down for 30 minutes.")
        return

    preferred = [n.lower() for n in action.params.get("preferred_contacts", [])]
    matches = [c for c in contacts if c["name"].lower() in preferred] if preferred else []
    chosen = random.choice(matches) if matches else random.choice(contacts)

    state.add_log(f"Laundering: selected contact {chosen['name']}.")
    _nav(_u(f"/income/laundering.asp?action=launder&id={chosen['id']}"), state)

    if not _check_session(state):
        return

    soup2 = BeautifulSoup(page.content(), "html.parser")

    max_amount = 0
    font_tag = soup2.find("font", size="1", string=re.compile(r"\$[\d,]+\s*max", re.IGNORECASE))
    if font_tag:
        m = re.search(r"\$([\d,]+)", font_tag.get_text())
        if m:
            max_amount = int(m.group(1).replace(",", ""))

    if max_amount <= 0:
        state.add_log("Laundering: could not parse max launder amount from page.")
        return

    configured = action.params.get("launder_amount", 0)
    if configured == 0:
        amount = min(max_amount, state.dirty_money)
    else:
        amount = min(max_amount, configured, state.dirty_money)

    amount_input = page.query_selector("input.input[name='amount']")
    if not amount_input:
        state.add_log("Laundering: amount input not found on page.")
        return

    amount_input.fill(str(amount))
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    state.add_log(f"Laundering: submitted ${amount:,} through {chosen['name']}.")


def handle_scrape_player(action: Action, state: GameState):
    username = action.params.get("username", "")
    if not username:
        return
    url = f"{urls.BASE_URL}/userprofile.asp?username={username}"
    page = browser.page()
    resp = page.goto(url, wait_until="domcontentloaded", timeout=15000)
    if not resp or resp.status != 200:
        state.add_log(f"Scrape: failed to load profile for {username}")
        return
    soup = BeautifulSoup(page.content(), "html.parser")
    data = {}
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True).rstrip(":").lower()
            val = cells[1].get_text(strip=True)
            if key == "sex":
                data["sex"] = val
            elif key == "wealth":
                data["wealth"] = val
            elif key == "scripting":
                data["scripting"] = val
    gf_holder = soup.find(id="profile_gf_holder")
    if gf_holder:
        gf_text = gf_holder.get_text(strip=True)
        if gf_text:
            data["godfather"] = gf_text
    crew_holder = soup.find(id="profile_crew_holder")
    if crew_holder:
        crew_text = crew_holder.get_text(strip=True)
        if crew_text:
            data["crew_name"] = crew_text
    regime_holder = soup.find(id="regime_holder")
    if regime_holder:
        capo_names = [a.get_text(strip=True) for a in regime_holder.find_all("a") if a.get_text(strip=True)]
        if capo_names:
            data["capos"] = ", ".join(capo_names)
    import player_db
    player_db.update_scraped_data(username, data)
    state.add_log(f"Scrape: updated profile for {username}")


# ---------------------------------------------------------------------------
# Skills handlers
# ---------------------------------------------------------------------------

def handle_discover_skills(action: Action, state: GameState):
    _nav(_u("/income/charskills.asp"), state)
    if not _check_session(state):
        return
    soup = BeautifulSoup(state.page_html, "html.parser")
    found = set()
    for form in soup.find_all("form", action=True):
        if "charskills.asp" not in form.get("action", ""):
            continue
        skill_input = form.find("input", attrs={"name": "skill", "type": "hidden"})
        if skill_input and skill_input.get("value"):
            found.add(skill_input["value"])
    state.available_skills = found
    if found:
        state.add_log(f"Skills: discovered {len(found)} — {', '.join(sorted(found))}")
    else:
        state.add_log("Skills: none unlocked.")
    _nav(_u("/main.asp"), state)


def handle_use_skill(action: Action, state: GameState):
    skill_id = action.params.get("skill_id", "")
    target = action.params.get("target", "")
    skill_name = action.params.get("skill_name", skill_id)
    update_respect = action.params.get("update_respect", False)

    _nav(_u("/income/charskills.asp"), state)
    if not _check_session(state):
        return
    page = browser.page()
    soup = BeautifulSoup(state.page_html, "html.parser")
    form = None
    for f in soup.find_all("form", action=True):
        si = f.find("input", attrs={"name": "skill", "type": "hidden"})
        if si and si.get("value") == skill_id:
            form = f
            break
    if not form:
        state.add_log(f"{skill_name}: skill form not found on page.")
        return
    rank_input = form.find("input", attrs={"name": "rank", "type": "hidden"})
    rank = rank_input["value"] if rank_input else "1"
    target_input = form.find("input", attrs={"name": "target"})
    if not target_input:
        state.add_log(f"{skill_name}: no target input found.")
        return
    form_idx = [f for f in soup.find_all("form", action=True)
                if "charskills.asp" in f.get("action", "")].index(form)
    selector = f"form:has(input[name='skill'][value='{skill_id}'])"
    page.fill(f"{selector} input[name='target']", target)
    page.click(f"{selector} input[name='doskill']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    result_soup = BeautifulSoup(state.page_html, "html.parser")
    success = result_soup.find("div", id="success")
    fail = result_soup.find("div", id="fail")
    if success:
        msg = success.get_text(strip=True)
        state.add_log(f"{skill_name} ({target}): {msg}")
        if update_respect:
            import re
            import player_db
            player_db.update_respect(target, msg)
    elif fail:
        state.add_log(f"{skill_name} ({target}): {fail.get_text(strip=True)}")
    else:
        text = result_soup.get_text(" ", strip=True)[:200]
        state.add_log(f"{skill_name} ({target}): {text}")


def handle_use_news_editor(action: Action, state: GameState):
    skill_id = action.params.get("skill_id", "")
    target = action.params.get("target", "")
    title = action.params.get("title", "")
    event = action.params.get("event", "")
    skill_name = action.params.get("skill_name", "News Editor")

    _nav(_u("/income/charskills.asp"), state)
    if not _check_session(state):
        return
    page = browser.page()
    selector = f"form:has(input[name='skill'][value='{skill_id}'])"
    soup = BeautifulSoup(state.page_html, "html.parser")
    form = None
    for f in soup.find_all("form", action=True):
        si = f.find("input", attrs={"name": "skill", "type": "hidden"})
        if si and si.get("value") == skill_id:
            form = f
            break
    if not form:
        state.add_log(f"{skill_name}: skill form not found on page.")
        return
    page.fill(f"{selector} input[name='title']", title[:30])
    page.fill(f"{selector} textarea[name='event']", event[:1000])
    page.fill(f"{selector} input[name='target']", target)
    page.click(f"{selector} input[name='doskill']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    result_soup = BeautifulSoup(state.page_html, "html.parser")
    success = result_soup.find("div", id="success")
    fail = result_soup.find("div", id="fail")
    if success:
        state.add_log(f"{skill_name} ({target}): {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"{skill_name} ({target}): {fail.get_text(strip=True)}")
    else:
        text = result_soup.get_text(" ", strip=True)[:200]
        state.add_log(f"{skill_name} ({target}): {text}")


HANDLERS = {
    "login": handle_login,
    "check_earns": handle_check_earns,
    "refresh_earn_catalog": handle_refresh_earn_catalog,
    "clear_earn_queue": handle_clear_earn_queue,
    "manual_earn": handle_manual_earn,
    "bulk_add_launder_contacts": handle_bulk_add_launder_contacts,
    "check_banking_cases": handle_check_banking_cases,
    "do_crime": handle_do_crime,
    "event_boss": handle_event_boss,
    "event_consume": handle_event_consume,
    "refresh_event_inventory": handle_refresh_event_inventory,
    "ws_monitor": handle_ws_monitor,
    "crossroad": handle_crossroad,
    "interact": handle_interact,
    "check_weapon": handle_check_weapon,
    "consume": handle_consume,
    "refresh_state": handle_refresh_state,
    "payback": handle_payback,
    "probe_agcrime":        handle_probe_agcrime,
    "check_bionics":        handle_check_bionics,
    "check_weapon_store":   handle_check_weapon_store,
    "check_drug_store":     handle_check_drug_store,
    "do_community_service": handle_community_service,
    "do_dog_trains": handle_do_dog_trains,
    "do_fire_duties": handle_fire_duties,
    "do_career_training": handle_career_training,
    "do_university":      handle_university,
    "do_training_centre": handle_training_centre,
    "do_armed_robbery": handle_armed_robbery,
    "do_torch_business": handle_torch_business,
    "do_drug_manufacturing": handle_drug_manufacturing,
    "launder_money": handle_launder_money,
    "check_hospital_cases": handle_check_hospital_cases,
    "check_fire_cases": handle_check_fire_cases,
    "check_engineering_cases": handle_check_engineering_cases,
    "jail_duties": handle_jail_duties,
    "jail_action": handle_jail_action,
    "jail_consume": handle_jail_consume,
    "clear_jail_duty_queue": handle_clear_jail_duty_queue,
    "deposit": handle_deposit,
    "withdraw": handle_withdraw,
    "jailbreak_plan": handle_jailbreak_plan,
    "jailbreak_execute": handle_jailbreak_execute,
    "jailbreak_calloff": handle_jailbreak_calloff,
    "check_journals": handle_check_journals,
    "archive_journals": handle_archive_journals,
    "journal_action": handle_journal_action,
    "check_drug_trade": handle_check_drug_trade,
    "do_blind_eye": handle_blind_eye,
    "check_warrants": handle_check_warrants,
    "turn_in_warrant": handle_turn_in_warrant,
    "apply_illness_treatment": handle_apply_illness_treatment,
    "do_gym": handle_gym,
    "play_casino": handle_casino,
    "do_bank_invest": handle_bank_invest,
    "check_vehicle": handle_check_vehicle,
    "repair_vehicle": handle_repair_vehicle,
    "travel": handle_travel,
    "fetch_respect": handle_fetch_respect,
    "fetch_profile": handle_fetch_profile,
    "navigate": handle_navigate,
    "scrape_player": handle_scrape_player,
    "discover_skills": handle_discover_skills,
    "use_skill": handle_use_skill,
    "use_news_editor": handle_use_news_editor,
}


class ActionExecutor:
    def execute(self, action: Action, state: GameState):
        handler = HANDLERS.get(action.kind)
        if handler:
            try:
                handler(action, state)
            except Exception as e:
                err = str(e)
                import re as _re

                # Build a human-readable log message
                if "Timeout" in err and "ms exceeded" in err:
                    ms_match = _re.search(r"(\d+)ms exceeded", err)
                    url_match = _re.search(r'navigating to "([^"]+)"', err)
                    ms = ms_match.group(1) if ms_match else "?"
                    url = url_match.group(1) if url_match else "?"
                    state.add_log(
                        f"Error executing {action.kind}: navigation timed out after {ms}ms — {url} "
                        f"(city={state.current_city}, logged_in={state.logged_in})"
                    )
                elif "interrupted by another navigation" in err:
                    url_match = _re.search(r'navigating to "([^"]+)"', err)
                    url = url_match.group(1) if url_match else "?"
                    state.add_log(
                        f"Error executing {action.kind}: navigation interrupted — {url} "
                        f"(another task likely navigated concurrently)"
                    )
                else:
                    state.add_log(f"Error executing {action.kind}: {e}")

                # Recovery — get the browser back to a known safe page
                if "Page crashed" in err or "has been closed" in err or "ERR_INSUFFICIENT_RESOURCES" in err:
                    state.add_log("Browser/page lost — restarting browser.")
                    try:
                        headless = cfg.load().get("misc", {}).get("headless", False)
                        browser.stop()
                        browser.start(headless=headless)
                        state.add_log("Browser restarted — will re-login on next tick.")
                        state.logged_in = False
                    except Exception as restart_err:
                        state.add_log(f"Browser restart failed: {restart_err}")
                elif any(kw in err for kw in ("Timeout", "interrupted by another navigation", "net::", "ERR_")):
                    state.add_log(f"Recovering from {action.kind} error — navigating to safe page.")
                    try:
                        page = browser.page()
                        page.goto(
                            _u("/loggedin.asp?display=play"),
                            wait_until="domcontentloaded",
                            timeout=15000,
                        )
                        _refresh_state(state)
                        state.add_log("Recovery successful.")
                    except Exception as rec_err:
                        state.add_log(f"Recovery navigation failed: {rec_err} — marking as logged out.")
                        state.logged_in = False
        else:
            state.add_log(f"No handler for action: {action.kind}")
