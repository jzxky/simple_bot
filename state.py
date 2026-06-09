"""
Shared game state. Parsed from the current page on each navigation.
All time comparisons use server time, never the system clock.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from bs4 import BeautifulSoup

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
    logged_in: bool = False
    relog_suppressed: bool = False
    current_url: str = ""
    bot_running: bool = False
    last_error: str = ""
    log: list = field(default_factory=list)
    timers: dict = field(default_factory=dict)
    agg_fail_times: list = field(default_factory=list)
    current_task: str = ""

    def agg_fail_count(self) -> int:
        cutoff = datetime.now() - timedelta(minutes=30)
        self.agg_fail_times = [t for t in self.agg_fail_times if t > cutoff]
        return len(self.agg_fail_times)

    def record_agg_fail(self):
        self.agg_fail_times.append(datetime.now())

    def in_home_city(self) -> bool:
        return self.current_city != "" and self.current_city == self.home_city

    def action_available(self) -> bool:
        if self.action_timer_ready:
            return True
        if self.action_timer_end and self.server_time:
            return self.server_time >= self.action_timer_end
        return False

    def add_log(self, message: str):
        ts = self.server_time.strftime("%H:%M:%S") if self.server_time else "?"
        entry = f"[{ts}] {message}"
        self.log.append(entry)
        if len(self.log) > 200:
            self.log = self.log[-200:]
        print(entry)


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
        except ValueError:
            pass

    # AggPro active — red name background is the definitive signal
    s.agg_pro_active = bool(soup.find("div", id="display_top", class_="display_red"))

    # nav_right fields — walk display_top labels
    for top in soup.find_all("div", id="display_top"):
        label = top.get_text(strip=True)
        nxt = top.find_next_sibling("div")
        if not nxt:
            continue
        text = nxt.get_text(strip=True)
        if "Name" in label:
            pass  # own name parsed via anchor below
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

    # Login state
    s.logged_in = url.rstrip("/") != "https://mafiamatrix.com/default.asp"

    return s
