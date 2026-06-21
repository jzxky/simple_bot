"""
Shared game state. Parsed from the current page on each navigation.
All time comparisons use server time, never the system clock.
"""

from __future__ import annotations
import re
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup
import urls

SERVER_TIME_FMT = "%m/%d/%Y %I:%M:%S %p"


@dataclass
class GameState:
    page_html: str = ""
    own_name: str = ""
    rank: str = ""
    occupation: str = ""
    current_city: str = ""
    home_city: str = ""
    energy: float = 0.0
    health: int = 100
    clean_money: int = 0
    dirty_money: int = 0
    bank_balance: int = 0
    next_rank: str = ""
    rank_progress: int = 0
    earns_24h: int = 0
    consumables_24h: int = 0
    consumables: dict = field(default_factory=dict)
    action_timer_ready: bool = False
    action_timer_end: Optional[datetime] = None
    agg_pro_active: bool = False
    agg_pro_end: Optional[datetime] = None
    server_time: Optional[datetime] = None
    server_time_monotonic: float = 0.0  # monotonic timestamp when server_time was last set
    logged_in: bool = False
    relog_suppressed: bool = False
    current_url: str = ""
    bot_running: bool = False
    last_error: str = ""
    log: list = field(default_factory=list)
    timers: dict = field(default_factory=dict)
    agg_fail_times: list = field(default_factory=list)
    current_task: str = ""
    snipe_top_job_pending: bool = False
    snipe_top_job_promo_url: str = ""
    in_jail: bool = False
    jail_rank: str = ""
    has_new_journals: bool = False
    journals_updated_at: float = 0.0
    jail_consumables: dict = field(default_factory=dict)
    jail_release_secs: "int | None" = None
    hold_action_timer: bool = False
    vehicle_health: "int | None" = None
    flight_departs_at: "float | None" = None
    char_history_updated_at: float = 0.0
    in_hospital: bool = False
    hospital_release_at: "float | None" = None
    cs_sentence: int = 0      # community services still owed as agg-crime punishment
    online_players: set = field(default_factory=set)   # all usernames in whosonlinecell
    local_players: set = field(default_factory=set)    # subset with * (same city as bot)
    notifications: list = field(default_factory=list)

    @property
    def ingame_mins(self) -> "int | None":
        if self.server_time is None:
            return None
        return self.server_time.hour * 60 + self.server_time.minute


    def agg_fail_count(self) -> int:
        cutoff = datetime.now() - timedelta(minutes=30)
        self.agg_fail_times = [t for t in self.agg_fail_times if t > cutoff]
        return len(self.agg_fail_times)

    def record_agg_fail(self):
        self.agg_fail_times.append(datetime.now())

    def in_home_city(self) -> bool:
        return self.current_city != "" and self.current_city == self.home_city

    def _estimated_server_time(self) -> "datetime | None":
        if not self.server_time:
            return None
        elapsed = _time.monotonic() - self.server_time_monotonic
        return self.server_time + timedelta(seconds=elapsed)

    def action_available(self) -> bool:
        if self.action_timer_ready:
            return True
        if self.action_timer_end:
            now = self._estimated_server_time()
            return now is not None and now >= self.action_timer_end
        return False

    def timer_ready(self, key: str) -> bool:
        t = self.timers.get(key, {})
        if t.get("ready", False):
            return True
        end = t.get("end")
        if end:
            now = self._estimated_server_time()
            return now is not None and now >= end
        return False

    def add_log(self, message: str):
        ts = self.server_time.strftime("%H:%M:%S") if self.server_time else "?"
        entry = f"[{ts}] {message}"
        self.log.append(entry)
        if len(self.log) > 200:
            self.log = self.log[-200:]
        print(entry)

    def push_notification(self, event_type: str, message: str):
        import time as _t
        ts = self.server_time.strftime("%H:%M:%S") if self.server_time else "?"
        self.notifications.append({
            "id": str(int(_t.time() * 1000)),
            "ts": ts,
            "event_type": event_type,
            "message": message,
        })


def _parse_money(text: str) -> int:
    return int(re.sub(r'[^0-9]', '', text) or 0)


def parse_state(html: str, url: str, existing: GameState) -> GameState:
    soup = BeautifulSoup(html, "html.parser")
    s = existing
    s.page_html = html
    s.current_url = url

    # Server time
    st = soup.find("div", class_="serverTime")
    if st:
        try:
            s.server_time = datetime.strptime(st.get_text(strip=True), SERVER_TIME_FMT)
            s.server_time_monotonic = _time.monotonic()
        except ValueError:
            pass

    # AggPro active — red name background is the definitive signal
    s.agg_pro_active = bool(soup.find("div", id="display_top", class_="display_red"))

    # New journals — any class other than plain "journal" means unread entries
    journal_span = soup.find("span", id="journals_span_id")
    if journal_span:
        s.has_new_journals = journal_span.get("class", ["journal"]) != ["journal"]

    # Jail detection — body class mm-in-jail is definitive; also check nav_right for "Jail Rank"
    body_el = soup.find("body")
    body_classes = body_el.get("class", []) if body_el else []
    s.in_jail = "mm-in-jail" in body_classes or any(
        "Jail Rank" in d.get_text(strip=True)
        for d in soup.find_all("div", id="display_top")
    )

    # Jail release countdown — find the div with data-date-end adjacent to donation_auctiontimer
    # that contains "until release" text. The span itself is JS-populated (empty in raw HTML).
    if s.in_jail and s.server_time:
        release_div = None
        for span in soup.find_all("span", class_="donation_auctiontimer"):
            parent = span.find_parent("div")
            if parent and "until release" in parent.get_text(strip=True).lower():
                release_div = parent
                break
        if release_div:
            end_str = release_div.get("data-date-end", "").strip()
            if end_str:
                try:
                    end_dt = datetime.strptime(end_str, SERVER_TIME_FMT)
                    secs = int((end_dt - s.server_time).total_seconds())
                    s.jail_release_secs = max(secs, 0) if secs >= 0 else None
                except ValueError:
                    pass
    elif not s.in_jail:
        s.jail_release_secs = None

    # Hospital detection — only the root-level hospital page, not localcity/hospital.asp
    import urls as _urls
    if url.rstrip("/") == _urls.BASE_URL + "/hospital.asp":
        s.in_hospital = True
        if s.server_time and s.hospital_release_at is None:
            # Look for "You will be released at:" followed by a datetime string
            text = soup.get_text(" ", strip=True)
            m = re.search(r"You will be released at[:\s]+(\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}:\d{2}\s+[AP]M)", text, re.IGNORECASE)
            if m:
                try:
                    release_dt = datetime.strptime(m.group(1).strip(), SERVER_TIME_FMT)
                    # Anchor using server_time offset from real time
                    offset = (release_dt - s.server_time).total_seconds()
                    import time as _time
                    s.hospital_release_at = _time.time() + offset
                except ValueError:
                    pass
    else:
        s.in_hospital = False
        s.hospital_release_at = None

    # nav_right fields — walk display_top labels
    for top in soup.find_all("div", id="display_top"):
        label = top.get_text(strip=True)
        nxt = top.find_next_sibling("div")
        if not nxt:
            continue
        text = nxt.get_text(strip=True)
        if "Name" in label:
            pass  # own name parsed via anchor below
        elif "Jail Rank" in label:
            s.jail_rank = text
        elif "Rank" in label and "Next" not in label:
            s.rank = text
        elif "Occupation" in label:
            s.occupation = text
        elif "Clean money" in label:
            s.clean_money = _parse_money(text)
        elif "Dirty money" in label:
            s.dirty_money = _parse_money(text)
        elif "Location" in label:
            s.current_city = text
        elif "Home City" in label:
            s.home_city = text

    # Own name
    display = soup.find("div", id="display")
    if display and display.find("a"):
        s.own_name = display.find("a").get_text(strip=True)

    # Health
    health_div = soup.find("div", id="display_bar")
    if health_div:
        hd = health_div.find("div", class_=lambda c: c and ("display_green" in c or "display_yellow" in c or "display_orange" in c or "display_red" in c))
        if hd:
            try:
                s.health = int(float(hd.get_text(strip=True).replace("%", "")))
            except (ValueError, TypeError):
                pass

    # Energy
    energy_bar = soup.find("div", class_="progress-bar bg-energy")
    if energy_bar:
        try:
            s.energy = float(energy_bar.get("aria-valuenow", 0))
        except (ValueError, TypeError):
            s.energy = 0.0

    # Next rank + rank progress
    next_rank_span = soup.find("span", class_="next_rank_txt")
    if next_rank_span:
        s.next_rank = next_rank_span.get_text(strip=True)
    rank_bar = soup.find("div", class_="progress-bar bg-rankprogress")
    if rank_bar:
        try:
            s.rank_progress = int(float(rank_bar.get("aria-valuenow", 0)))
        except (ValueError, TypeError):
            pass

    # Earns in last 24h
    earns_bar = soup.find("div", class_="progress-bar bg-earns")
    if earns_bar:
        try:
            s.earns_24h = int(float(earns_bar.get("aria-valuenow", 0)))
        except (ValueError, TypeError):
            pass

    # Consumables used in last 24h (display_top label → display_end value)
    for top in soup.find_all("div", id="display_top"):
        if "Consumables / 24h" in top.get_text():
            nxt = top.find_next_sibling("div", id="display_end")
            if nxt:
                try:
                    s.consumables_24h = int(nxt.get_text(strip=True))
                except (ValueError, TypeError):
                    pass
            break

    # Consumables inventory (from inline JS object)
    script = soup.find("script", string=re.compile(r"var consumables"))
    if script:
        matches = re.findall(r'"(\w+)":\s*(\d+)', script.string)
        s.consumables = {k: int(v) for k, v in matches}

    # All timers from #user_timers_holder
    timers = {}
    holder = soup.find("div", id="user_timers_holder")
    if holder:
        for form in holder.find_all("form"):
            name = form.get("name", "")
            if not name:
                continue
            span = form.find("span", class_="donation_timer")
            if not span:
                continue
            ready_span = span.find("span", style=lambda v: v and "00bb01" in v)
            if ready_span:
                timers[name] = {"ready": True, "end": None}
            else:
                end_str = span.get("data-date-end", "")
                end_dt = None
                if end_str:
                    try:
                        end_dt = datetime.strptime(end_str.strip(), SERVER_TIME_FMT)
                    except ValueError:
                        pass
                timers[name] = {"ready": False, "end": end_dt}
    s.timers = timers

    # Derive action timer fields from timers dict
    action_t = timers.get("action", {})
    s.action_timer_ready = action_t.get("ready", False)
    s.action_timer_end = action_t.get("end")

    # Derive aggpro end time from timers dict (active state already set above)
    aggpro_t = timers.get("aggpro", {})
    s.agg_pro_end = aggpro_t.get("end")

    # Jail consumables — parsed whenever contraband.asp is loaded
    if "contraband.asp" in url:
        _JAIL_ITEM_MAP = {
            "Cigarettes:": "cigarettes", "Cigarettes": "cigarettes",
            "Booze:": "booze", "Booze": "booze",
            "Heroin:": "heroin", "Heroin": "heroin",
            "Porn:": "porn", "Porn": "porn",
            "Shanks:": "shanks", "Shanks": "shanks",
        }
        jail_cons = {}
        for row in soup.find_all("tr"):
            tds = row.find_all("td")
            # Each row has pairs: label td, value td (display_border), repeated
            i = 0
            while i < len(tds) - 1:
                label = tds[i].get_text(strip=True)
                key = _JAIL_ITEM_MAP.get(label)
                if key:
                    try:
                        jail_cons[key] = int(tds[i + 1].get_text(strip=True))
                    except (ValueError, TypeError):
                        jail_cons[key] = 0
                    i += 2
                else:
                    i += 1
        if jail_cons:
            s.jail_consumables = jail_cons

    # Bank balance — parsed whenever bank.asp is loaded
    if "bank.asp" in url:
        for strong in soup.find_all("strong"):
            if "Bank Balance" in strong.get_text():
                sib = strong.find_next_sibling(string=True) or (strong.parent.get_text(strip=True) if strong.parent else "")
                try:
                    s.bank_balance = _parse_money(str(sib))
                except Exception:
                    pass
                break

    # Online/local players — two whosonlinecell divs: class contains "global" or "local"
    def _parse_woc(div) -> set:
        names = set()
        for a in div.find_all("a", id=True):
            pid = a.get("id", "")
            if not pid.startswith("profileLink:"):
                continue
            parts = pid.split(":")
            if len(parts) >= 2:
                names.add(parts[1])
        return names

    global_woc = soup.find("div", id="whosonlinecell", class_="global")
    local_woc  = soup.find("div", id="whosonlinecell", class_="local")
    if global_woc or local_woc:
        s.online_players = _parse_woc(global_woc) if global_woc else set()
        s.local_players  = _parse_woc(local_woc)  if local_woc  else set()

    # Login state
    s.logged_in = url.rstrip("/") != urls.BASE_URL + "/default.asp"

    return s
