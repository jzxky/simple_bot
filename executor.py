"""
ActionExecutor: maps Action.kind to handler functions that drive the browser.
"""

import json
import re
import time
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
TRANSFER_URL = "https://mafiamatrix.com/income/bank.asp?option=transfers"
USERS_URL = "https://mafiamatrix.com/skin/updateusers.php?q=1"

ONLINE_CRIMES = {"pickpocket", "mugging"}
RESIDENT_CRIMES = {"hack", "breaking"}

QUEUE_MIN = 10
QUEUE_MAX = 200

MUGGING_WEAPONS = {"Baseball Bat", "Pistol"}
BODY_PARTS = {"Arms", "Legs", "Eyes", "Brain", "Heart"}


def _refresh_state(state: GameState):
    html = browser.page().content()
    url = browser.current_url()
    parse_state(html, url, state)


def _nav(url: str, state: GameState):
    html = browser.navigate(url)
    parse_state(html, browser.current_url(), state)


def _check_session(state: GameState) -> bool:
    """Return True if still logged in, False if redirected to login page."""
    if "default.asp" in browser.current_url() and "loggedin" not in browser.current_url():
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

    # Enable AUTO mode — check if the auto panel is hidden, if so click the knob to toggle
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

    # Read queue count
    soup = BeautifulSoup(page.content(), "html.parser")
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
    return bool(page.query_selector("input[type='text']"))


def _back_to_target_input(crime: str, state: GameState) -> bool:
    """Go back one step; fall back to full navigation if text input isn't there."""
    page = browser.page()
    page.go_back(wait_until="domcontentloaded")
    if page.query_selector("input[type='text']"):
        return True
    return _nav_to_target_input(crime, state)


def handle_do_crime(action: Action, state: GameState):
    crime = action.params["crime"]
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

    for player in targets:
        if not page.query_selector("input[type='text']"):
            if not _back_to_target_input(crime, state):
                state.add_log("Lost target input mid-loop. Aborting.")
                return

        page.fill("input[type='text']", player)
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
            if "weapon" in fail_msg.lower():
                state.add_log("Weapon required — equipping and retrying.")
                handle_check_weapon(Action("check_weapon", crime=crime), state)
                if not _back_to_target_input(crime, state):
                    return
                page.fill("input[type='text']", player)
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
                continue
            state.add_log(f"Crime failed vs {player}, trying next.")
            continue

    state.add_log("All targets exhausted.")


def handle_check_weapon(action: Action, state: GameState):
    crime = action.params["crime"]
    page = browser.page()
    _nav(PROFILE_URL, state)

    if not _check_session(state):
        return

    soup = BeautifulSoup(page.content(), "html.parser")
    weapons_div = soup.find("div", class_="showWeapons")
    if not weapons_div:
        state.add_log("Could not find weapons div.")
        return

    tables = weapons_div.find_all("table", class_="item_table")
    equipped_names = set()
    stash_slots = []  # list of (weapon_name, carry_url)

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
            # try finding action row differently
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

    if crime == "mugging":
        needed = MUGGING_WEAPONS
    else:
        needed = None  # armed robbery: any non-body-part

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
            page.wait_for_load_state("domcontentloaded")
            _refresh_state(state)
            return

    state.add_log(f"No valid weapon found for {crime}. Skipping crime.")
    # Signal crime task to skip by marking no weapon — handled by AggCrimeTask resetting




def handle_payback(action: Action, state: GameState):
    amount = action.params["amount"]
    target = action.params["target"]
    page = browser.page()
    _nav(TRANSFER_URL, state)

    if not _check_session(state):
        return

    page.fill("input[name='transferamount']", str(amount))
    page.fill("input[name='transfername']", target)
    page.click("input[name='B1']")
    page.wait_for_load_state("domcontentloaded")
    _refresh_state(state)
    state.add_log(f"Payback sent: ${amount:,} to {target}.")


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


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

HANDLERS = {
    "login": handle_login,
    "check_earns": handle_check_earns,
    "do_crime": handle_do_crime,
    "check_weapon": handle_check_weapon,
    "payback": handle_payback,
    "do_community_service": handle_community_service,
    "do_career_training": handle_career_training,
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
