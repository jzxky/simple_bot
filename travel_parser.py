"""
Parse travel destinations and whether each city is open or closed.

Two pages list destinations:
  - /travel/travel.asp (own vehicle): one <div class="city-container"> per city,
    holding a <div class="city-travel-container" id="<City>"> with a line like
        <p>This city has a lockdown status of <font color="red">Closed</font></p>
    and a depart.asp?destination=... link. A closed (locked-down) city still has
    a depart link — entering it violates the lockdown — so the status line is
    what decides open/closed. The page also has a mobile list
    (#mm-travel-mobile) where a locked city's row has class "mm-locked" and a
    "LOCKDOWN" badge; it's used as a fallback when the status line is missing.
  - /travel/airport.asp (flights): <select name="destination"> with one <option>
    per city. Its lockdown format isn't known yet, so a disabled option or
    "closed"/"lockdown" in the label is treated as closed.
"""

import re

from bs4 import BeautifulSoup

_DEPART_RE = re.compile(r"depart\.asp\?destination=", re.I)
_CLOSED_RE = re.compile(r"\b(closed|lockdown)\b", re.I)
_LOCKDOWN_RE = re.compile(r"lockdown status of\s*(\w+)", re.I)


def _has_closed_marker(tag) -> bool:
    """True if the tag or any descendant carries a 'closed'/'locked' class."""
    for el in [tag, *tag.find_all(True)]:
        classes = el.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        if any("closed" in c.lower() or "locked" in c.lower() for c in classes):
            return True
    return False


def _lockdown_status(container) -> str:
    """'Open' / 'Closed' from the "lockdown status of ..." line, or ''."""
    m = _LOCKDOWN_RE.search(container.get_text(" ", strip=True))
    return m.group(1) if m else ""


def _mobile_locked(soup) -> "dict[str, bool]":
    """City (lower-cased) -> locked, from the #mm-travel-mobile radio list."""
    locked = {}
    mobile = soup.find(id="mm-travel-mobile")
    if not mobile:
        return locked
    for row in mobile.find_all("label", class_="mm-travel-row"):
        radio = row.find("input", attrs={"name": "mm-travel-dest"})
        if not radio or not radio.get("value"):
            continue
        classes = row.get("class") or []
        locked[radio["value"].strip().lower()] = (
            "mm-locked" in classes
            or row.find(class_="mm-travel-lockdown-badge") is not None
        )
    return locked


def parse_vehicle_destinations(html: str) -> "list[dict]":
    """Destinations on travel.asp.

    Returns [{"name", "open", "status", "href", "reason"}]; status is the
    lockdown status text ("Open"/"Closed", "" if not shown), href the depart
    link ("" when absent), reason explains why a city is closed.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    mobile = _mobile_locked(soup)
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
        status = _lockdown_status(inner)
        if status:
            reason = "" if status.lower() == "open" else f"lockdown status {status}"
        elif mobile.get(name.lower()):
            reason = "lockdown"
        elif not href:
            reason = "no depart link"
        else:
            reason = ""
        results.append({"name": name, "open": not reason, "status": status,
                         "href": href, "reason": reason})
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
