"""
ActionExecutor: maps Action.kind to handler functions that drive the browser.
"""

import json
import re
import time
import config as cfg
import urls
from bs4 import BeautifulSoup
from tasks.base import Action
from state import GameState, parse_state
import browser


def _u(path: str) -> str:
    return urls.BASE_URL + path


def _notify(state: GameState, event_type: str, message: str):
    if cfg.load().get("notifications", {}).get(event_type, False):
        state.push_notification(event_type, message)

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

QUEUE_MIN = 10
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
}

ARMED_MAX_RETRIES = 6


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
        state.add_log(f"Earns detected — auto: [{auto_labels}] | manual: [{manual_labels}]")
    else:
        state.add_log("Earns: no options detected on earn page.")

    return auto_opts, available_values


def handle_refresh_earn_catalog(action: Action, state: GameState):
    """Scrape the earn page and update available_earns.json — no queue action."""
    _scrape_earn_catalog(browser.page(), state)


def handle_check_earns(action: Action, state: GameState):
    earn_type = action.params["earn_type"]
    page = browser.page()

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
    cap_span = BeautifulSoup(page.content(), "html.parser").find("span", class_="mm-earn-queue-cap")
    current_count = 0
    if cap_span:
        try:
            current_count = int(cap_span.get_text(strip=True).split("/")[0].strip())
        except (ValueError, IndexError):
            pass

    if current_count >= QUEUE_MIN:
        state.add_log(f"Earn queue at {current_count}/200, no top-up needed.")
        return

    top_up = QUEUE_MAX - current_count
    state.add_log(f"Earn queue at {current_count}/200, topping up by {top_up}.")

    page.select_option("select[name='schedule_earn_identifier']", earn_type)
    page.fill("input[name='schedule_count']", str(top_up))
    page.click("button.mm-earn-add-btn")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log("Earn queue topped up.")


def handle_clear_earn_queue(action: Action, state: GameState):
    page = browser.page()
    _nav(_u("/income/earn.asp"), state)

    if not _check_session(state):
        return

    # Ensure AUTO panel is visible
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
            _flush_fails()
            _nav(_u("/loggedin.asp?display=play"), state)
            return

    _flush_fails()
    state._agg_targets_exhausted = True
    state.add_log("All targets exhausted.")


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
        page.check("input[name='csinothercities'][value='hospital']")
        state.add_log("Community service (away city): assist local civilians")

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
        state.add_log(f"Career training: {msg} — disabling actions.")
        c = cfg.load()
        c["action"]["enabled"] = False
        cfg.save(c)
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
        state.add_log(f"Career training: reached {current_trains} trains — stop-at-14 reached, disabling actions.")
        c = cfg.load()
        c["action"]["enabled"] = False
        cfg.save(c)
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
                is_public = name in PUBLIC_BUSINESSES
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

            state.add_log(f"No valid armed robbery target (pass {pass_num}, attempt {attempt + 1}/{ARMED_MAX_RETRIES}).")

        # retries exhausted — check if another task needs to run
        state.add_log(f"Armed robbery: no targets after pass {pass_num}. Checking task queue...")
        if check_other_tasks and check_other_tasks():
            state.add_log("Another task is ready — yielding armed robbery.")
            _nav(_u("/loggedin.asp?display=play"), state)
            return
        state.add_log("No other tasks pending — retrying armed robbery.")


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
    state.add_log("Drug manufacturing: submitted.")



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
    {"label": "Whore",                               "schedule_value": "whore",              "data_earn": "0",    "category": "Secret",      "available": True},
    {"label": "Streetfight",                         "schedule_value": "street_fight",        "data_earn": "1",    "category": "Secret",      "available": True},
    {"label": "Joyride",                             "schedule_value": "joy_ride",            "data_earn": None,   "category": "Secret",      "available": None},
    {"label": "Pimp",                                "schedule_value": "pimp",               "data_earn": None,   "category": "Secret",      "available": None},
    {"label": "Shoplift",                            "schedule_value": "shoplift",            "data_earn": "2",    "category": "Crime",       "available": True},
    {"label": "Steal Cheques",                       "schedule_value": "steal_cheques",       "data_earn": None,   "category": "Crime",       "available": None},
    {"label": "Nurse at local hospital",             "schedule_value": "nurse",               "data_earn": "3",    "category": "Hospital",    "available": True},
    {"label": "Doctor at local hospital",            "schedule_value": "doctor",              "data_earn": None,   "category": "Hospital",    "available": None},
    {"label": "Surgeon at local hospital",           "schedule_value": "surgeon",             "data_earn": None,   "category": "Hospital",    "available": None},
    {"label": "Hospital Director",                   "schedule_value": "hospital_director",   "data_earn": None,   "category": "Hospital",    "available": None},
    {"label": "Mechanic at local vehicle yard",      "schedule_value": "mechanic",            "data_earn": "4",    "category": "Engineering", "available": True},
    {"label": "Technician at local vehicle yard",    "schedule_value": "technician",          "data_earn": "5",    "category": "Engineering", "available": True},
    {"label": "Engineer at local Construction Site", "schedule_value": "engineer",            "data_earn": "6",    "category": "Engineering", "available": True},
    {"label": "Work at local bank",                  "schedule_value": "bank_teller",         "data_earn": "7",    "category": "Bank",        "available": True},
    {"label": "Mortician Assistant",                 "schedule_value": "mortician_assistant", "data_earn": "8",    "category": "Mortician",   "available": True},
    {"label": "Legal Secretary",                     "schedule_value": "legal_secretary",     "data_earn": "10",   "category": "Law",         "available": True},
    {"label": "Drag racing",                         "schedule_value": "drag_racing",         "data_earn": None,   "category": "Crime",       "available": None},
    {"label": "Hack bank account",                   "schedule_value": "hack_bank",           "data_earn": None,   "category": "Crime",       "available": None},
    {"label": "Scamming",                            "schedule_value": "scamming",            "data_earn": None,   "category": "Crime",       "available": None},
    {"label": "Pizza Restaurant",                    "schedule_value": None,                  "data_earn": "Pizza","category": "General",     "available": False},
    {"label": "Local 7/11",                          "schedule_value": None,                  "data_earn": "711",  "category": "General",     "available": False},
    {"label": "Bar/Nightclub",                       "schedule_value": None,                  "data_earn": "Bar",  "category": "General",     "available": False},
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

    auto_labels = set()
    for val, label in auto_opts:
        auto_labels.add(label)
        if label in by_label:
            by_label[label]["schedule_value"] = val
            by_label[label]["available"] = True
        else:
            by_label[label] = {"label": label, "schedule_value": val, "data_earn": None,
                               "available": True, "category": "Uncategorized"}

    for data_earn, label, is_trap in manual_opts:
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


def handle_clear_jail_duty_queue(action: Action, state: GameState):
    page = browser.page()
    _nav(_u("/jail/duties.asp"), state)

    if not _check_session(state):
        return

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

    btn = page.query_selector("button.mm-earn-queue-clear-btn")
    if not btn:
        state.add_log("Clear jail duty queue button not found.")
        return

    btn.click()
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log("Jail duty queue cleared.")


def handle_jail_duties(action: Action, state: GameState):
    duty = action.params["duty"]
    page = browser.page()
    _nav(_u("/jail/duties.asp"), state)

    if not _check_session(state):
        return

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
            state.add_log("Jail duties: switched to AUTO mode.")

    soup = BeautifulSoup(page.content(), "html.parser")
    auto_panel = soup.find("div", class_="mm-earn-mode-auto")
    available_values = []
    if auto_panel:
        sel = auto_panel.find("select", attrs={"name": "schedule_earn_identifier"})
        if sel:
            available_values = [o.get("value", "") for o in sel.find_all("option")]

    chosen = duty if duty in available_values else (available_values[-1] if available_values else None)
    if not chosen:
        state.add_log("Jail duties: no duty options available on page.")
        return

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

    radio = page.query_selector(f"input[type='radio'][value='{jail_action}']")
    if not radio:
        state.add_log(f"Jail action: radio for '{jail_action}' not found on page.")
        return

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


def handle_check_bionics(action: Action, state: GameState):
    from tasks.bionics import BIONIC_PRICES, REVERSE_ORDER
    import config as cfg
    wanted = cfg.load().get("bionics", {}).get("wanted_items", [])
    task = action.params.get("_task")

    if not wanted:
        state.add_log("Bionics: no wanted items configured.")
        return

    # Items to consider in reverse price order
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
        from tasks.bionics import save_last_bionics_check
        task.last_checked_at = time.time()
        save_last_bionics_check(task.last_checked_at)

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

        # Stash before next purchase
        _nav(_u("/profile/default.asp"), state)
        stash_link = page.query_selector("a[href='/weapons.asp?action=stash1']")
        if not stash_link:
            state.add_log("Bionics: stash #1 not available — stopping.")
            break
        stash_link.click()
        page.wait_for_load_state("domcontentloaded")
        stash_soup = BeautifulSoup(page.content(), "html.parser")
        if stash_soup.find("div", id="fail"):
            state.add_log(f"Bionics: stash failed — stopping.")
            break
        state.add_log("Bionics: stashed in slot #1.")

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
# Journal handlers
# ---------------------------------------------------------------------------

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
                data[e["id"]] = e
                changed = True
        break

    if changed:
        _save_journals(char, data)
        state.journals_updated_at = time.time()

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
    _nav(url, state)
    soup = BeautifulSoup(state.page_html, "html.parser")
    success = soup.find("div", id="success")
    fail = soup.find("div", id="fail")
    if success:
        state.add_log(f"Warrant {case_id}: turned in — {success.get_text(strip=True)}")
    elif fail:
        state.add_log(f"Warrant {case_id}: failed — {fail.get_text(strip=True)}")
    else:
        state.add_log(f"Warrant {case_id}: submitted.")


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
    soup = BeautifulSoup(state.page_html, "html.parser")
    if _NO_VEHICLE_TEXT in state.page_html.lower():
        state.add_log("Check vehicle: no vehicle available.")
        state.vehicle_health = None
        return 0
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
    target = action.params.get("target_city", "")
    method = action.params.get("method", "airport")

    if not target:
        state.add_log("Travel: no target city specified.")
        return 0

    if state.current_city.lower() == target.lower():
        state.add_log(f"Travel: already in {target}.")
        return 1

    if method == "own_vehicle":
        pct = handle_check_vehicle(Action("check_vehicle"), state)
        if state.vehicle_health is None:
            return 0
        if pct == 0:
            ok = handle_repair_vehicle(Action("repair_vehicle"), state)
            return 1 if ok else 0
        _nav(_u(_DEPART_URL) + f"?destination={target}", state)
        if not _check_session(state):
            return 0
        state.add_log(f"Travel: departing to {target} by vehicle.")
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
        state.add_log("Gym: travelling to Chicago...")
        result = handle_travel(Action("travel", target_city=_CHICAGO, method="airport"), state)
        if result == 0:
            state.add_log("Gym: travel to Chicago failed — skipping.")
            return
        if state.current_city != _CHICAGO:
            state.add_log(f"Gym: still not in Chicago after travel ({state.current_city}) — skipping.")
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
    # Read only from the portion of the page before the first column_title section,
    # so section-level divs don't shadow the top-level result message.
    search_root = result_soup
    holder = result_soup.find("div", id="holder_content")
    if holder:
        pre = []
        for child in holder.children:
            if hasattr(child, "get") and "column_title" in child.get("class", []):
                break
            pre.append(str(child))
        if pre:
            search_root = BeautifulSoup("".join(pre), "html.parser")
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


HANDLERS = {
    "login": handle_login,
    "check_earns": handle_check_earns,
    "refresh_earn_catalog": handle_refresh_earn_catalog,
    "clear_earn_queue": handle_clear_earn_queue,
    "do_crime": handle_do_crime,
    "check_weapon": handle_check_weapon,
    "consume": handle_consume,
    "refresh_state": handle_refresh_state,
    "payback": handle_payback,
    "probe_agcrime":        handle_probe_agcrime,
    "check_bionics":        handle_check_bionics,
    "do_community_service": handle_community_service,
    "do_fire_duties": handle_fire_duties,
    "do_career_training": handle_career_training,
    "do_armed_robbery": handle_armed_robbery,
    "do_drug_manufacturing": handle_drug_manufacturing,
    "check_hospital_cases": handle_check_hospital_cases,
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
    "check_drug_trade": handle_check_drug_trade,
    "check_warrants": handle_check_warrants,
    "turn_in_warrant": handle_turn_in_warrant,
    "apply_illness_treatment": handle_apply_illness_treatment,
    "do_gym": handle_gym,
    "play_casino": handle_casino,
    "check_vehicle": handle_check_vehicle,
    "repair_vehicle": handle_repair_vehicle,
    "travel": handle_travel,
    "fetch_respect": handle_fetch_respect,
}


class ActionExecutor:
    def execute(self, action: Action, state: GameState):
        handler = HANDLERS.get(action.kind)
        if handler:
            try:
                handler(action, state)
            except Exception as e:
                state.add_log(f"Error executing {action.kind}: {e}")
                if "Page crashed" in str(e):
                    state.add_log("Page crashed — restarting browser.")
                    try:
                        headless = cfg.load().get("misc", {}).get("headless", False)
                        browser.stop()
                        browser.start(headless=headless)
                        state.add_log("Browser restarted after crash.")
                        state.logged_in = False
                    except Exception as restart_err:
                        state.add_log(f"Browser restart failed: {restart_err}")
        else:
            state.add_log(f"No handler for action: {action.kind}")
