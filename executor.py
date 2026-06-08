"""
ActionExecutor: maps Action.kind to handler functions that drive the browser.
"""

import json
import re
import time
import config as cfg
from bs4 import BeautifulSoup
from tasks.base import Action
from state import GameState, parse_state
import browser

LOGIN_URL = "https://mafiamatrix.com/default.asp"
PLAY_URL = "https://mafiamatrix.com/loggedin.asp?display=play"
PROFILE_URL = "https://mafiamatrix.com/profile/default.asp"
CRIME_URL = "https://mafiamatrix.com/income/agcrime.asp"
EARN_URL = "https://mafiamatrix.com/income/earn.asp"
CS_URL = "https://mafiamatrix.com/income/communityservice.asp"
FD_URL = "https://mafiamatrix.com/income/fireduties.asp"
DM_URL = "https://mafiamatrix.com/income/manufacture.asp"
INCOME_URL = "https://mafiamatrix.com/income/income.asp"
TRANSFER_URL = "https://mafiamatrix.com/income/bank.asp?option=transfers"
USERS_URL = "https://mafiamatrix.com/skin/updateusers.php?q=1"
BIZ_URL = "https://mafiamatrix.com/business/business.asp"
HOSPITAL_CASES_URL = "https://mafiamatrix.com/localcity/hospital.asp?display=patients"

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

ARMED_MAX_RETRIES = 12


def _refresh_state(state: GameState):
    html = browser.page().content()
    url = browser.current_url()
    parse_state(html, url, state)


def _nav(url: str, state: GameState):
    html = browser.navigate(url)
    parse_state(html, browser.current_url(), state)


def _check_session(state: GameState) -> bool:
    """Return True if still logged in, False if redirected to login page."""
    if browser.current_url().rstrip("/") == "https://mafiamatrix.com/default.asp":
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

    page.goto(LOGIN_URL, wait_until="load")

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
        page.goto(PLAY_URL, wait_until="load")
        _refresh_state(state)

    state.logged_in = True
    state.add_log("Logged in successfully.")


def handle_check_earns(action: Action, state: GameState):
    earn_type = action.params["earn_type"]
    page = browser.page()
    _nav(EARN_URL, state)

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
    _nav(EARN_URL, state)

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
    browser.page().goto(USERS_URL, wait_until="domcontentloaded", timeout=15000)
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
    _nav(CRIME_URL, state)
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
    state.add_log(f"Selected crime: {crime}")

    failed_transfers: set = set()

    for player in targets:
        if player in failed_transfers:
            continue

        if threshold and state.energy < threshold:
            state.add_log(f"Energy {state.energy}% dropped below threshold {threshold}% — stopping.")
            return

        if not page.query_selector(_TARGET_INPUT):
            if not _back_to_target_input(crime, state):
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
            state.add_log(f"Crime failed vs {player}: {fail_msg}")
            if "weapon" in fail_msg.lower():
                state.add_log("Weapon check disabled, skipping target.")
                continue
            if crime == "hack" and "increased security" in fail_msg.lower():
                continue
            if crime == "hack" and "no money in their account" in fail_msg.lower():
                state.add_log(f"No money in {player}'s account — sending $1 to unlock, then retrying.")
                if not _back_to_target_input(crime, state):
                    state.add_log("Lost target input after no-money fail. Aborting.")
                    return
                ok = _do_transfer(player, 1, state)
                if not ok:
                    state.add_log(f"Transfer to {player} failed — skipping for this run.")
                    failed_transfers.add(player)
                    if not _nav_to_target_input(crime, state):
                        state.add_log("Could not return to crime page. Aborting.")
                        return
                    continue
                # Navigate back to crime page and retry this player
                if not _nav_to_target_input(crime, state):
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
                    state.add_log(f"Retry failed vs {player}: {retry_fail.get_text(strip=True)}")
                continue
            if crime in ("pickpocket", "mugging", "breaking") and "recently survived" in fail_msg.lower():
                continue
            _nav(PLAY_URL, state)
            return

    state._agg_targets_exhausted = True
    state.add_log("All targets exhausted.")


def handle_check_weapon(action: Action, state: GameState):
    crime = action.params["crime"]
    page = browser.page()
    page.goto(PROFILE_URL, wait_until="load", timeout=30000)
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
                        carry_link = "https://mafiamatrix.com" + a["href"]
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




def handle_consume(action: Action, state: GameState):
    consume_type = action.params["type"]
    url = f"https://mafiamatrix.com/profile/consumables.asp?action=consume&type={consume_type}"
    _nav(url, state)
    soup = BeautifulSoup(browser.page().content(), "html.parser")
    msg_div = soup.find("div", id="success") or soup.find("div", id="fail")
    msg = msg_div.get_text(strip=True) if msg_div else "No result."
    state.add_log(f"Consume {consume_type}: {msg}")


def handle_refresh_state(action: Action, state: GameState):
    _nav(PLAY_URL, state)


def handle_payback(action: Action, state: GameState):
    amount = action.params["amount"]
    target = action.params["target"]
    page = browser.page()

    for attempt in range(2):
        _nav(TRANSFER_URL, state)

        if not _check_session(state):
            return

        page.fill("input[name='transferamount']", str(amount))
        page.fill("input[name='transfername']", target)
        page.click("input[name='B1']")
        page.wait_for_load_state("domcontentloaded")

        soup = BeautifulSoup(page.content(), "html.parser")
        result_text = soup.get_text()

        if "Your transfer was blocked due to possible spam!" in result_text:
            state.add_log(f"Payback to {target} blocked as spam — retrying in 60s.")
            time.sleep(60)
            continue

        _refresh_state(state)
        state.add_log(f"Payback sent: ${amount:,} to {target}.")
        return

    state.add_log(f"Payback to {target} blocked twice — giving up.")


def handle_community_service(action: Action, state: GameState):
    in_home = action.params["in_home_city"]
    page = browser.page()
    _nav(CS_URL, state)

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
    _nav(FD_URL, state)

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
    _nav(TRANSFER_URL, state)
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
    browser.page().goto(USERS_URL, wait_until="domcontentloaded", timeout=15000)
    try:
        data = json.loads(browser.page().inner_text("body"))
    except Exception:
        state.add_log("Failed to parse users for public business payback.")
        return
    recipient = next(
        (p["userName"] for p in data
         if p.get("userCity") == state.current_city and p.get("userJob") == job),
        None,
    )
    if not recipient:
        state.add_log(f"No {job} found in {state.current_city} for payback.")
        return
    _do_transfer(recipient, amount, state)


def _payback_private_business(business_name: str, amount: int, state: GameState):
    _nav(BIZ_URL, state)
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
    _nav(CRIME_URL, state)
    if not _check_session(state):
        return
    if threshold and state.energy < threshold:
        state.add_log(f"Energy {state.energy}% dropped below threshold {threshold}% — aborting.")
        return
    page.check("input[name='agcrime'][value='armed']")
    page.click("input[type='submit'][name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)

    for attempt in range(ARMED_MAX_RETRIES):
        if attempt > 0:
            time.sleep(5)
            page.once("dialog", lambda d: d.accept())
            page.reload(wait_until="domcontentloaded")
            _refresh_state(state)

        soup = BeautifulSoup(page.content(), "html.parser")
        select = soup.find("select", attrs={"name": "armed"})
        if not select:
            state.add_log("Armed robbery: business select not found.")
            _nav(PLAY_URL, state)
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
                state.add_log(f"Armed robbery failed: {fail_div.get_text(strip=True)}")
            else:
                state.add_log("Armed robbery: unexpected result page.")
            _nav(PLAY_URL, state)
            return

        state.add_log(f"No valid armed robbery target (attempt {attempt + 1}/{ARMED_MAX_RETRIES}).")

    state.add_log("Armed robbery: no valid targets after 12 attempts.")
    state._agg_targets_exhausted = True
    _nav(PLAY_URL, state)


def handle_drug_manufacturing(action: Action, state: GameState):
    page = browser.page()
    _nav(DM_URL, state)

    if not _check_session(state):
        return

    if INCOME_URL in browser.current_url():
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


_HOSPITAL_EMPTY_MARKERS = [
    "There are currently no patients",
    "There are currently no DNA samples",
]


def _save_casework_snapshot(name: str, html: str):
    import datetime
    site_map_dir = os.path.join(paths.data_dir(), "site_map")
    os.makedirs(site_map_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(os.path.join(site_map_dir, f"{name}_{ts}.html"), "w", encoding="utf-8") as f:
        f.write(html)
    png = browser.page().screenshot()
    with open(os.path.join(site_map_dir, f"{name}_{ts}.png"), "wb") as f:
        f.write(png)


def handle_check_hospital_cases(action: Action, state: GameState):
    _nav(HOSPITAL_CASES_URL, state)

    if not _check_session(state):
        return

    html = browser.page().content()
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", attrs={"border": "1"})
    if not table:
        return

    table_text = table.get_text()
    if all(marker in table_text for marker in _HOSPITAL_EMPTY_MARKERS):
        return  # nothing to do

    state.add_log("Hospital: case work available — saving snapshot for analysis.")
    _save_casework_snapshot("hospital", html)


# ---------------------------------------------------------------------------
# Executor
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
