"""
Parse travel destinations and whether each city is open or closed.

Two pages list destinations:
  - /travel/travel.asp (own vehicle): one <div class="city-container"> per city,
    holding a <div class="city-travel-container" id="<City>"> with a
    depart.asp?destination=... link when the city can be travelled to.
  - /travel/airport.asp (flights): <select name="destination"> with one <option>
    per city.

A city counts as closed when the page says so ("closed" in its text, or a
class/id containing "closed"), when its airport option is disabled, or — on
travel.asp — when it has no depart link.
"""

import re

from bs4 import BeautifulSoup

_DEPART_RE = re.compile(r"depart\.asp\?destination=", re.I)
_CLOSED_RE = re.compile(r"\bclosed\b", re.I)


def _has_closed_marker(tag) -> bool:
    """True if the tag or any descendant carries a 'closed' class/id."""
    for el in [tag, *tag.find_all(True)]:
        classes = el.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        if any("closed" in c.lower() for c in classes):
            return True
        if "closed" in (el.get("id") or "").lower():
            return True
    return False


def _closed_reason(tag) -> str:
    """The text that marks the city closed, or '' if none found."""
    text = tag.get_text(" ", strip=True)
    m = _CLOSED_RE.search(text)
    if m:
        # Keep a short snippet around the match for logging.
        start = max(0, m.start() - 40)
        return text[start:m.end() + 40].strip()
    if _has_closed_marker(tag):
        return "marked closed"
    return ""


def parse_vehicle_destinations(html: str) -> "list[dict]":
    """Destinations on travel.asp.

    Returns [{"name", "open", "href", "reason"}]; href is the depart link
    ("" when absent), reason explains why a city is closed.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    results = []
    for div in soup.find_all("div", class_="city-container"):
        inner = div.find("div", class_="city-travel-container")
        if not inner:
            continue
        name = (inner.get("id") or "").strip()
        if not name:
            continue
        link = inner.find("a", href=_DEPART_RE)
        href = link["href"] if link else ""
        reason = _closed_reason(div)
        if not reason and not href:
            reason = "no depart link"
        results.append({"name": name, "open": not reason, "href": href, "reason": reason})
    return results


def parse_airport_destinations(html: str) -> "list[dict]":
    """Destinations in the airport.asp dropdown.

    Returns [{"name", "label", "open", "reason", "costs", "minutes"}].
    """
    soup = BeautifulSoup(html or "", "html.parser")
    sel = soup.find("select", attrs={"name": "destination"})
    if not sel:
        return []
    results = []
    for o in sel.find_all("option"):
        value = o.get("value", "")
        if not value or value == "0":
            continue
        label = o.get_text(strip=True)
        reason = ""
        if o.has_attr("disabled"):
            reason = "disabled in dropdown"
        elif _CLOSED_RE.search(label):
            reason = label
        elif _has_closed_marker(o):
            reason = "marked closed"
        results.append({
            "name": value,
            "label": label,
            "open": not reason,
            "reason": reason,
            "costs": o.get("data-costs", ""),
            "minutes": o.get("data-minutes", ""),
        })
    return results


def find_destination(dests: "list[dict]", city: str) -> "dict | None":
    """Case-insensitive lookup of a city in a parsed destination list."""
    city = (city or "").lower()
    return next((d for d in dests if d["name"].lower() == city), None)
