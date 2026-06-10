"""
Fetch, parse, and cache character history from playerstats.asp.
Stored as JSON in the data directory.
"""

import json
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
import browser
import paths

CACHE_PATH = os.path.join(paths.data_dir(), "character_history.json")
STATS_URL = "https://mafiamatrix.com/stats/playerstats.asp"

_CAREER_SECTIONS = {
    "Mayor", "Funeral Work", "Banking Work", "Customs Work",
    "Medical Work", "Law Work", "Police Work", "Engineering", "Fire Fighter",
}


def _parse(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    stat_sections = []
    promotion_history = []
    skills_traits = []

    for table in soup.find_all("table", id="playerstats"):
        # Check for Promotion History (4 header cols: City, Rank, Occupation, Date)
        headers = [th.get_text(strip=True) for th in table.find_all("th")]
        if headers == ["City", "Rank", "Occupation", "Date"]:
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) >= 4:
                    promotion_history.append({
                        "city": cells[0].get_text(strip=True),
                        "rank": cells[1].get_text(strip=True),
                        "occupation": cells[2].get_text(strip=True),
                        "date": cells[3].get_text(strip=True),
                    })
            continue

        # Skills & Traits Summary (headers include "Name" and "Status")
        if "Name" in headers and "Status" in headers:
            for tr in table.find_all("tr"):
                cells = tr.find_all("td")
                if len(cells) >= 4:
                    # Determine type from row class or first-cell content
                    row_type = "Skill" if "skill" in (tr.get("class") or [""]) else "Trait"
                    name = cells[0].get_text(strip=True)
                    rank_text = cells[1].get_text(strip=True)  # e.g. "0/2"
                    rank, max_rank = 0, 0
                    m = re.match(r"(\d+)/(\d+)", rank_text)
                    if m:
                        rank, max_rank = int(m.group(1)), int(m.group(2))
                    status = cells[2].get_text(strip=True)
                    used = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                    if name:
                        skills_traits.append({
                            "type": row_type,
                            "name": name,
                            "rank": rank,
                            "max_rank": max_rank,
                            "status": status,
                            "used": used,
                        })
            continue

        # Standard stat tables: first row is the section title (colspan), rest are key/value rows
        title_cell = table.find("td", attrs={"colspan": True})
        if not title_cell:
            continue
        title = title_cell.get_text(strip=True)

        # Skip Earn History — granular breakdown already tracked by bot
        if title == "Earn History":
            continue

        rows = []
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) == 2 and not cells[0].get("colspan"):
                key = cells[0].get_text(strip=True)
                val = cells[1].get_text(strip=True)
                if key:
                    rows.append({"key": key, "value": val})

        career = title in _CAREER_SECTIONS
        stat_sections.append({"title": title, "rows": rows, "career": career})

    return {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stat_sections": stat_sections,
        "promotion_history": promotion_history,
        "skills_traits": skills_traits,
    }


def fetch_and_save() -> dict:
    html = browser.navigate(STATS_URL)
    data = _parse(html)
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return data


def load() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
