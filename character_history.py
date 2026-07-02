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

CACHE_PATH = os.path.join(paths.data_dir(), "character_history.json")  # legacy / current character


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name or "")


def _per_char_path(name: str) -> str:
    return os.path.join(paths.data_dir(), f"chistory_{_safe(name)}.json")


def has_saved(name: str) -> bool:
    """True if a per-character history file already exists for this name."""
    return bool(name) and os.path.exists(_per_char_path(name))

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

        # ── Standard stat tables: single-cell "Key: Value" or two-cell rows ─
        section_rows = []
        for tr in rows[1:]:  # skip title row
            cells = tr.find_all("td")
            if len(cells) == 1:
                text = cells[0].get_text(strip=True)
                if ":" not in text:
                    continue
                key, _, val = text.partition(":")
                key = key.strip()
                val = val.strip()
                if key:
                    section_rows.append({"key": key, "value": val})
            elif len(cells) == 2:
                key = cells[0].get_text(strip=True).rstrip(":")
                val = cells[1].get_text(strip=True)
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


def fetch_and_save(char_name: str = "", alive_lookup: bool = False) -> "dict | None":
    """Fetch and save a character's history.

    - alive_lookup=False: the current character (playerstats.asp).
    - alive_lookup=True: another player by name (playerstatsalive.asp?u=name).

    Returns the parsed data, or None if the page had no stats table (navigation
    unsuccessful / no such page)."""
    if alive_lookup:
        url = urls.BASE_URL + "/stats/playerstatsalive.asp?u=" + char_name
    else:
        url = urls.BASE_URL + "/stats/playerstats.asp"
    html = browser.navigate(url)
    soup = BeautifulSoup(html, "html.parser")
    if not soup.find("table", id="playerstats"):
        return None

    data = _parse(html)
    if char_name:
        data["character"] = char_name
    os.makedirs(paths.data_dir(), exist_ok=True)
    if char_name:
        with open(_per_char_path(char_name), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    # The current character also writes the legacy file so the default view is unchanged.
    if not alive_lookup:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    return data


def load(name: str = "") -> dict:
    """Load a saved character history. name="" → current character (legacy file)."""
    path = _per_char_path(name) if name else CACHE_PATH
    if not os.path.exists(path):
        # fall back to legacy for the current character
        if name and os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            if d.get("character") == name:
                return d
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_saved() -> list:
    """Return the names of all saved character histories (sorted)."""
    names = set()
    d = paths.data_dir()
    try:
        entries = os.listdir(d)
    except FileNotFoundError:
        return []
    for fn in entries:
        if fn.startswith("chistory_") and fn.endswith(".json"):
            try:
                with open(os.path.join(d, fn), "r", encoding="utf-8") as f:
                    nm = json.load(f).get("character")
            except Exception:
                nm = fn[len("chistory_"):-len(".json")]
            if nm:
                names.add(nm)
    # Include the current character from the legacy file
    if os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                nm = json.load(f).get("character")
            if nm:
                names.add(nm)
        except Exception:
            pass
    return sorted(names)
