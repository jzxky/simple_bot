"""
Shared game state. Parsed from the current page on each navigation.
All time comparisons use server time, never the system clock.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup


@dataclass
class GameState:
    page_html: str = ""
    own_name: str = ""
    current_city: str = ""
    home_city: str = ""
    energy: int = 0
    action_timer_ready: bool = False
    action_timer_end: Optional[datetime] = None
    agg_pro_active: bool = False
    agg_pro_end: Optional[datetime] = None
    server_time: Optional[datetime] = None
    logged_in: bool = False
    current_url: str = ""
    bot_running: bool = False
    last_error: str = ""
    log: list = field(default_factory=list)
    timers: dict = field(default_factory=dict)

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


SERVER_TIME_FMT = "%m/%d/%Y %I:%M:%S %p"


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

    # Own name
    display = soup.find("div", id="display")
    if display and display.find("a"):
        s.own_name = display.find("a").get_text(strip=True)

    # Cities — find all display_top labels then read following siblings
    tops = soup.find_all("div", id="display_top")
    for top in tops:
        label = top.get_text(strip=True)
        nxt = top.find_next_sibling("div")
        if nxt:
            if "Location" in label and nxt.get("id") == "display":
                s.current_city = nxt.get_text(strip=True)
            elif "Home City" in label and nxt.get("id") == "display_end":
                s.home_city = nxt.get_text(strip=True)

    # Energy
    energy_bar = soup.find("div", class_="progress-bar bg-energy")
    if energy_bar:
        try:
            s.energy = int(energy_bar.get("aria-valuenow", 0))
        except (ValueError, TypeError):
            s.energy = 0

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

    # Derive aggpro fields from timers dict
    aggpro_t = timers.get("aggpro", {})
    s.agg_pro_active = not aggpro_t.get("ready", True)
    s.agg_pro_end = aggpro_t.get("end")

    # Login state
    s.logged_in = "default.asp" not in url or "loggedin" in url

    return s
