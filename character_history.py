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
import urls
import paths

CACHE_PATH = os.path.join(paths.data_dir(), "character_history.json")

_CAREER_SECTIONS = {
    "Mayor", "Funeral Work", "Banking Work", "Customs Work",
    "Medical Work", "Law Work", "Police Work", "Engineering", "Fire Fighter",
}


def _parse_int(text: str) -> int:
    try:
        return int(re.sub(r'[^0-9]', '', text) or 0)
    except Exception:
        return 0


def _parse(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    stat_sections = []
    promotion_history = []
    earn_history = []
    skills_traits = []

    for table in soup.find_all("table", id="playerstats"):
        rows = table.find_all("tr")
        if not rows:
            continue

        # Identify table by its first title cell
        title_cell = rows[0].find("td")
        if not title_cell:
            continue
        title = title_cell.get_text(strip=True)

        # ── Promotion History ──────────────────────────────────────────────
        if "Promotion History" in title:
            for tr in rows[2:]:  # skip title row and header row
                cells = tr.find_all("td")
                if len(cells) >= 4:
                    promotion_history.append({
                        "city": cells[0].get_text(strip=True),
                        "rank": cells[1].get_text(strip=True),
                        "occupation": cells[2].get_text(strip=True),
                        "date": cells[3].get_text(strip=True),
                    })
            continue

        # ── Skills & Traits ────────────────────────────────────────────────
        if "Character Skills and Traits" in title:
            for tr in rows[2:]:  # skip title and header
                cells = tr.find_all("td")
                if len(cells) < 3:
                    continue
                # First cell: "<strong>Trait:</strong> Name" or "<strong>Skill:</strong> Name"
                cell0 = cells[0]
                strong = cell0.find("strong")
                if not strong:
                    continue
                row_type = strong.get_text(strip=True).rstrip(":")
                name = cell0.get_text(strip=True)
                # strip "Trait: " or "Skill: " prefix
                name = re.sub(r'^(Trait|Skill):\s*', '', name)

                # Second cell: "Rank X of Y"
                rank_text = cells[1].get_text(strip=True)
                rank, max_rank = 0, 0
                m = re.search(r'(\d+)\s+of\s+(\d+)', rank_text)
                if m:
                    rank, max_rank = int(m.group(1)), int(m.group(2))

                # Third cell: status span
                status_span = cells[2].find("span")
                status = status_span.get_text(strip=True) if status_span else cells[2].get_text(strip=True)

                used_text = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                used = 0 if used_text in ("X", "") else _parse_int(used_text)

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

        # ── Earn History ───────────────────────────────────────────────────
        if "Earn History" in title:
            for tr in rows[1:]:  # skip title row
                cells = tr.find_all("td")
                if len(cells) < 2:
                    continue
                category = cells[0].get_text(strip=True)
                if not category:
                    continue
                entries = []
                for cell in cells[1:]:
                    # Each cell: "EarnType:<br>count" — get_text with separator
                    text = cell.get_text(separator="\n", strip=True)
                    parts = text.split("\n")
                    if len(parts) >= 2:
                        earn_type = parts[0].rstrip(":")
                        count = _parse_int(parts[1])
                        entries.append({"type": earn_type, "count": count})
                if entries:
                    earn_history.append({"category": category, "entries": entries})
            continue

        # ── Standard single-column stat tables (Key: Value per row) ───────
        section_rows = []
        for tr in rows[1:]:  # skip title row
            cells = tr.find_all("td")
            if len(cells) != 1:
                continue
            text = cells[0].get_text(strip=True)
            if ":" not in text:
                continue
            key, _, val = text.partition(":")
            key = key.strip()
            val = val.strip()
            if key:
                section_rows.append({"key": key, "value": val})

        career = title in _CAREER_SECTIONS
        if section_rows:
            stat_sections.append({"title": title, "rows": section_rows, "career": career})

    return {
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "stat_sections": stat_sections,
        "earn_history": earn_history,
        "promotion_history": promotion_history,
        "skills_traits": skills_traits,
    }


def fetch_and_save() -> dict:
    html = browser.navigate(urls.BASE_URL + "/stats/playerstats.asp")
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
