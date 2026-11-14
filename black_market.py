"""
black_market.py — read the in-game black market and share its prices.

The market page (/income/BlackMarket.asp) lists each item with one price,
used for both buying and selling, and how many units this character holds
("Purchased"). Characters without enough crime XP are redirected away from
the page; that puts the check on a 1 hour cooldown.
"""

import re
import threading
import time
from datetime import datetime, timezone

from bs4 import BeautifulSoup

PATH = "/income/BlackMarket.asp"
UNAVAILABLE_COOLDOWN_SECS = 3600

_lock = threading.Lock()
_unavailable_until = 0.0
_last_seen: "dict | None" = None  # latest parsed market, for the trading step


def _money(text: str) -> "int | None":
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def is_market_url(url: str) -> bool:
    """False once the game has redirected away from the market page."""
    return "blackmarket.asp" in (url or "").lower()


def parse_market(html: str) -> "dict | None":
    """Parse the market page.

    Returns {"prices": {item: price}, "held": {item: units},
    "sell_cap": int|None, "sold_24h": int|None}, or None when the page has
    no market table.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    form = soup.find("form", action=lambda a: a and "blackmarketsale.asp" in a.lower())
    if not form:
        return None
    prices, held = {}, {}
    for row in form.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4 or "column_title" in (cells[1].get("class") or []):
            continue
        item = cells[1].get_text(strip=True)
        price = _money(cells[2].get_text(strip=True))
        if not item or not price:
            continue
        prices[item] = price
        units = _money(cells[3].get_text(strip=True))
        held[item] = units or 0
    if not prices:
        return None

    sell_cap = sold = None
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Maximum amount allowed to be sold\s*/\s*24 hours:\s*\$([\d,]+)", text)
    if m:
        sell_cap = _money(m.group(1))
    m = re.search(r"Amount you have sold\s*/\s*24 hours:\s*\$([\d,]+)", text)
    if m:
        sold = _money(m.group(1))
    return {"prices": prices, "held": held, "sell_cap": sell_cap, "sold_24h": sold}


def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def mark_unavailable():
    global _unavailable_until
    with _lock:
        _unavailable_until = time.monotonic() + UNAVAILABLE_COOLDOWN_SECS


def unavailable_remaining() -> int:
    """Seconds left on the not-available cooldown (0 when none)."""
    with _lock:
        return max(0, int(_unavailable_until - time.monotonic()))


def remember(city: str, market: dict):
    global _last_seen
    with _lock:
        _last_seen = dict(market, city=city, checked_at=utc_now_str(), seen_mono=time.monotonic())


def last_seen() -> "dict | None":
    with _lock:
        return dict(_last_seen) if _last_seen else None
