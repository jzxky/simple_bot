"""
black_market_trade.py — buy low here, sell high in the next city.

Pure planning functions (plan_sells, plan_buys) plus the holdings file that
remembers what was bought, at what cost, and the character's carry limit.
The executor (handle_black_market_trade / handle_black_market_sell) reads
the market page, asks these functions what to do and submits the form.

Rules from the game:
- One price per item, used for buying and selling.
- Every buy and sell needs the trafficking timer free.
- Selling is capped per 24 hours (shown on the page).
- The carry limit depends on vehicle and hidden factors; buying an
  impossibly large amount (PROBE_UNITS) makes the fail message state it.
- Travel cost is not part of the profit maths.
"""

import json
import os
import re
import threading
import time

import config as cfg
import paths

PROBE_UNITS = 300
MAX_UNITS_PER_SUBMIT = 999
CARRY_LIMIT_RECHECK_SECS = 24 * 3600

DEFAULTS = {
    "trading_enabled": False,
    "max_data_age_min": 60,
    "min_profit_pct": 10,
    "max_spend": 0,      # 0 = no cap
    "keep_cash": 0,
}

_lock = threading.Lock()


def settings() -> dict:
    raw = cfg.load().get("black_market", {})
    out = dict(DEFAULTS)
    for k, default in DEFAULTS.items():
        v = raw.get(k, default)
        if isinstance(default, bool):
            out[k] = bool(v)
        else:
            try:
                out[k] = max(0, float(v)) if k == "min_profit_pct" else max(0, int(v))
            except (TypeError, ValueError):
                out[k] = default
    return out


# ---- Holdings file ----

def _path() -> str:
    return os.path.join(paths.data_dir(), "black_market.json")


def load() -> dict:
    with _lock:
        try:
            with open(_path(), "r") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
    data.setdefault("lots", {})          # item -> {"units": int, "cost": avg price, "city": bought in}
    data.setdefault("carry_limit", None)
    data.setdefault("carry_limit_checked", 0)
    data.setdefault("vehicle", "")
    return data


def save(data: dict):
    with _lock:
        tmp = _path() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, _path())


def reconcile(data: dict, held: dict) -> dict:
    """Trim recorded lots to what the game says is held (manual sells, dumps)."""
    for item in list(data["lots"]):
        units = int(held.get(item, 0) or 0)
        if units <= 0:
            del data["lots"][item]
        elif units < data["lots"][item]["units"]:
            data["lots"][item]["units"] = units
    return data


def record_buy(data: dict, item: str, units: int, price: int, city: str):
    lot = data["lots"].get(item)
    if lot and lot["units"] > 0:
        total = lot["units"] + units
        lot["cost"] = round((lot["cost"] * lot["units"] + price * units) / total)
        lot["units"] = total
        lot["city"] = city
    else:
        data["lots"][item] = {"units": units, "cost": price, "city": city}


def record_sell(data: dict, item: str, units: int):
    lot = data["lots"].get(item)
    if not lot:
        return
    lot["units"] -= units
    if lot["units"] <= 0:
        del data["lots"][item]


def carry_limit_stale(data: dict, vehicle: str) -> bool:
    if not data.get("carry_limit"):
        return True
    if vehicle and vehicle != data.get("vehicle", ""):
        return True
    return time.time() - float(data.get("carry_limit_checked") or 0) > CARRY_LIMIT_RECHECK_SECS


def parse_carry_limit(fail_text: str) -> "int | None":
    """The most units the character can hold, from the fail message of an
    over-sized buy. None when the message is about something else (money,
    the trafficking timer)."""
    text = (fail_text or "").lower()
    if not text or "money" in text or "cash" in text or "try again shortly" in text:
        return None
    nums = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", text)]
    nums = [n for n in nums if 0 < n < PROBE_UNITS]
    return nums[0] if nums else None


# ---- Planning ----

def profit_pct(buy: int, sell: int) -> float:
    return (sell - buy) * 100.0 / buy if buy else 0.0


def plan_sells(market: dict, lots: dict, min_pct: float, target_prices: "dict | None" = None) -> dict:
    """{item: units} to sell here: each held lot whose local price clears cost
    plus min_pct, and (before travel) is at least the target city's price.
    Capped by the remaining 24 hour sell room."""
    prices = market.get("prices", {})
    held = market.get("held", {})
    room = None
    if market.get("sell_cap") is not None:
        room = max(0, market["sell_cap"] - (market.get("sold_24h") or 0))
    out = {}
    order = sorted(lots.items(), key=lambda kv: -profit_pct(kv[1]["cost"], prices.get(kv[0], 0)))
    for item, lot in order:
        price = prices.get(item)
        units = min(lot["units"], int(held.get(item, 0) or 0))
        if not price or units <= 0:
            continue
        if profit_pct(lot["cost"], price) < min_pct:
            continue
        if target_prices and target_prices.get(item, 0) > price:
            continue  # worth more where we're going
        if room is not None:
            units = min(units, room // price)
            if units <= 0:
                continue
            room -= units * price
        out[item] = units
    return out


def plan_buys(market: dict, target_prices: dict, min_pct: float, budget: int, room: "int | None") -> list:
    """[(item, units, price, pct)] to buy here for the target city, best margin
    first, within the cash budget and carry room (None = unknown, probe first)."""
    prices = market.get("prices", {})
    picks = []
    for item, price in prices.items():
        tp = target_prices.get(item)
        if not price or not tp:
            continue
        pct = profit_pct(price, tp)
        if pct >= min_pct:
            picks.append((pct, item, price))
    picks.sort(reverse=True)
    out = []
    for pct, item, price in picks:
        units = budget // price
        if room is not None:
            units = min(units, room)
        units = min(units, MAX_UNITS_PER_SUBMIT)
        if units <= 0:
            continue
        out.append((item, units, price, round(pct, 1)))
        budget -= units * price
        if room is not None:
            room -= units
    return out


def spend_budget(clean_money: int, s: dict, floor: int = 0) -> int:
    budget = max(0, clean_money - max(s["keep_cash"], floor))
    if s["max_spend"]:
        budget = min(budget, s["max_spend"])
    return budget
