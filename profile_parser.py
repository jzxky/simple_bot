"""
Parse the profile-page fields the Player Hub stores (userprofile.asp).

Status, home city and occupation come from the skins JSON; respect only from
All Seeing Eye — so only sex, wealth, scripting, clothing, pet,
accomplishments and medals are read here.
"""

import os
import re

from bs4 import BeautifulSoup

_SIMPLE_FIELDS = {"sex": "sex", "wealth": "wealth", "scripting": "scripting"}
_PET_FIELDS = {"breed": "breed", "age": "age", "fights won": "fights_won", "fights lost": "fights_lost"}


def _norm(text: str) -> str:
    return text.strip().rstrip(":").strip().lower()


def _cell_pairs(row):
    """(key, value) pairs from a row laid out as key: value [key: value ...]."""
    cells = row.find_all("td", recursive=False) or row.find_all(["td", "th"])
    out = []
    i = 0
    while i + 1 < len(cells):
        key = cells[i].get_text(" ", strip=True)
        if key.endswith(":"):
            out.append((_norm(key), cells[i + 1].get_text(" ", strip=True)))
            i += 2
        else:
            i += 1
    return out


def _table_with_cell(soup, label: str):
    """Innermost table holding a cell whose text is exactly `label`."""
    for td in soup.find_all(["td", "th"]):
        if td.get_text(" ", strip=True).lower() == label.lower():
            return td.find_parent("table"), td
    return None, None


def _icon_names(soup, heading: str) -> list:
    """Icon names (title/alt, else image file name) listed under a section heading."""
    head = soup.find(string=re.compile(re.escape(heading), re.I))
    if not head:
        return []
    container = head.find_parent("table") or head.parent
    nxt = container.find_next_sibling() if container else None
    images = []
    # The icons sit in the block after the heading block; fall back to the heading's table.
    for scope in (nxt, container):
        if scope is None:
            continue
        images = scope.find_all("img")
        if images:
            break
    names = []
    for img in images:
        name = img.get("title") or img.get("alt") or os.path.splitext(os.path.basename(img.get("src", "")))[0]
        name = name.strip()
        if name and name not in names:
            names.append(name)
    return names


def parse_profile(html: str, username: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    data = {"username": username}

    for row in soup.find_all("tr"):
        for key, val in _cell_pairs(row):
            if key in _SIMPLE_FIELDS and _SIMPLE_FIELDS[key] not in data:
                data[_SIMPLE_FIELDS[key]] = val

    table, head = _table_with_cell(soup, "Clothing:")
    if table is not None:
        clothing = {}
        for row in table.find_all("tr"):
            for key, val in _cell_pairs(row):
                if key != "clothing":
                    clothing[key.title()] = val
        data["clothing"] = clothing

    table, breed = _table_with_cell(soup, "Breed:")
    if table is not None:
        pet = {}
        first = table.find("tr")
        if first is not None:
            name = first.get_text(" ", strip=True)
            if name and not name.endswith(":"):
                pet["name"] = name
        for row in table.find_all("tr"):
            for key, val in _cell_pairs(row):
                if key in _PET_FIELDS:
                    pet[_PET_FIELDS[key]] = val
        data["pet"] = pet

    data["accomplishments"] = _icon_names(soup, "Character Accomplishments")
    data["medals"] = _icon_names(soup, "Account Medals")
    return data
