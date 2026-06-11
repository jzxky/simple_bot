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
    "booze": "Booze",
    "porn": "Porn",
    "shanks": "Shanks",
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
    "Airport", "Construction Company", "Bank"
}

PUBLIC_JOB_MAP = {
    "Funeral Parlour": "Funeral Director",
    "Town Hall": "Mayor",
    "Hospital": "Hospital Director",
    "Fire Station": "Fire Chief",
    "Airport": "Commissioner-General",
    "Construction Company": "Chief Engineer",
    "Bank": "Bank Manager",
}

ARMED_MAX_RETRIES = 6


def _refresh_state(state: GameState):
    html = browser.page().content()
    url = browser.current_url()
    parse_state(html, url, state)


def _nav(url: str, state: GameState):
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


def handle_check_earns(action: Action, state: GameState):
    earn_type = action.params["earn_type"]
    page = browser.page()
    _nav(_u("/income/earn.asp"), state)

    if not _check_session(state):
        return

    # Enable AUTO mode first — check if the auto panel is hidden, if so click the knob to toggle
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

    # Check earn is available by looking for it in the schedule select inside the auto panel
    soup = BeautifulSoup(page.content(), "html.parser")
    auto_panel = soup.find("div", class_="mm-earn-mode-auto")
    available_values = []
    if auto_panel:
        sel = auto_panel.find("select", attrs={"name": "schedule_earn_identifier"})
        if sel:
            available_values = [o.get("value", "") for o in sel.find_all("option")]

    if earn_type not in available_values:
        state.add_log(f"Earn '{earn_type}' is not available — disabling earns. Select a new earn and save to re-enable.")
        c = cfg.load()
        c["earns"]["enabled"] = False
        cfg.save(c)
        return

    # Read queue count
    cap_span = soup.find("span", class_="mm-earn-queue-cap")
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
        parts = a.get("id", "").split(":")
        if len(parts) < 3:
            continue
        name, status = parts[1], parts[2]
        if status == "In-Jail" or name == state.own_name:
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


def handle_do_crime(action: Action, state: GameState):
    crime = action.params["crime"]
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

    soup = BeautifulSoup(page.content(), "html.parser")
    select = soup.find("select", attrs={"name": "action"})
    if not select:
        state.add_log(f"Career training form not found for {career}.")
        return

    options = select.find_all("option")
    # Initial enroll: value contains "accept" or "begin training"
    # Ongoing study: value is "Yes"
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


def _payback_public_business(business_name: str, amount: int, state: GameState):
    job = PUBLIC_JOB_MAP.get(business_name)
    if not job:
        state.add_log(f"No job mapping for {business_name}.")
        return
    browser.page().goto(_u("/skin/updateusers.php?q=1"), wait_until="domcontentloaded", timeout=15000)
    try:
        data = json.loads(browser.page().inner_text("body"))
    except Exception:
        state.add_log("Failed to parse users for public business payback.")
        return
    recipient = next(
        (p["userName"] for p in data
         if p.get("userHomeCity") == state.home_city and p.get("userOccupation") == job),
        None,
    )
    if not recipient:
        state.add_log(f"No {job} found in {state.home_city} for payback.")
        return
    _do_transfer(recipient, amount, state)


def _payback_private_business(business_name: str, amount: int, state: GameState):
    _nav(_u("/business/business.asp"), state)
    soup = BeautifulSoup(browser.page().content(), "html.parser")
    owner = None
    for row in soup.select("table tr"):
        cells = row.find_all("td", class_="display_border")
        if len(cells) >= 2 and cells[0].get_text(strip=True) == business_name:
            a = cells[1].find("a")
            if a:
                owner = a.get_text(strip=True)
            break
    if not owner:
        state.add_log(f"Owner of {business_name} not found (may be Hidden).")
        return
    _do_transfer(owner, amount, state)


def handle_armed_robbery(action: Action, state: GameState):
    agg_private = action.params.get("agg_private", False)
    agg_drug_house = action.params.get("agg_drug_house", False)
    payback_private = action.params.get("payback_private", False)
    payback_public = action.params.get("payback_public", False)
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
        state.add_log("Armed crime option not available — aborting.")
        return
    page.check("input[name='agcrime'][value='armed']")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

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

                result_soup = BeautifulSoup(page.content(), "html.parser")
                success_div = result_soup.find("div", id="success")
                if success_div:
                    msg = success_div.get_text(strip=True)
                    state.add_log(f"Armed robbery success ({name}): {msg}")
                    amounts = re.findall(r"\$([\d,]+)", msg)
                    stolen = int(amounts[0].replace(",", "")) if amounts else 0
                    if stolen > 0:
                        if is_public and payback_public:
                            _payback_public_business(name, stolen, state)
                        elif is_private and not is_drug_house and payback_private:
                            _payback_private_business(name, stolen, state)
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
        state.add_log("Jail consume: no suitable consumables available (porn/booze/cigarettes).")
        return

    radio = page.query_selector(f"input[type='radio'][value='{consumable}']")
    if not radio:
        state.add_log(f"Jail consume: radio for '{consumable}' not found on page.")
        return

    page.check(f"input[type='radio'][value='{consumable}']")
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
        offer_url = f"{_u("/income/drugtrade.asp")}?display=offer&offerid={offer_id}"
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
                total_willing += max_price

        item_summary = ", ".join(
            f"{qty}x {raw_name}" for raw_name, _, qty in items
        )
        state.add_log(
            f"Drug trade offer {offer_id} [{item_summary}] "
            f"price=${offer_price:,} willing=${total_willing:,}"
        )

        if total_willing < offer_price:
            reason = "; ".join(decline_reasons) if decline_reasons else "price too high"
            state.add_log(f"Drug trade offer {offer_id}: declining ({reason}).")
            decline_url = f"{_u("/income/drugtrade.asp")}?action=decline&offerid={offer_id}"
            _nav(decline_url, state)
            continue

        # Funding check — dirty money only
        if state.dirty_money < offer_price:
            state.add_log(
                f"Drug trade: insufficient dirty money (have ${state.dirty_money:,}, "
                f"need ${offer_price:,}) — disabling autobuy."
            )
            c2 = cfg.load()
            c2.setdefault("autobuy", {})["enabled"] = False
            cfg.save(c2)
            return

        # Accept
        accept_url = f"{_u("/income/drugtrade.asp")}?action=accept&offerid={offer_id}"
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

HANDLERS = {
    "login": handle_login,
    "check_earns": handle_check_earns,
    "clear_earn_queue": handle_clear_earn_queue,
    "do_crime": handle_do_crime,
    "check_weapon": handle_check_weapon,
    "consume": handle_consume,
    "refresh_state": handle_refresh_state,
    "payback": handle_payback,
    "do_community_service": handle_community_service,
    "do_fire_duties": handle_fire_duties,
    "do_career_training": handle_career_training,
    "do_armed_robbery": handle_armed_robbery,
    "do_drug_manufacturing": handle_drug_manufacturing,
    "check_hospital_cases": handle_check_hospital_cases,
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
}


class ActionExecutor:
    def execute(self, action: Action, state: GameState):
        handler = HANDLERS.get(action.kind)
        if handler:
            try:
                handler(action, state)
            except Exception as e:
                state.add_log(f"Error executing {action.kind}: {e}")
        else:
            state.add_log(f"No handler for action: {action.kind}")
