"""
Drug middling task — triggered by !middle commands received via in-game comms,
or manually via the UI. Runs in the drug window (drug_window.py), not the main
browser window.
"""

import queue
import re
import threading
import time

from tasks.base import Task, Action
from state import GameState, norm_rank

MIDDLING_RANKS = {"piciotto", "enforcer", "dealer", "giovane d'honore"}
_HOME_CITY_REQUIRED_RANKS = {"enforcer", "dealer", "giovane d'honore"}
# The supply side: these ranks buy from the drug house and take dealers on as contacts.
DRUG_HOUSE_RANKS = {"sgarrista", "capodecima", "caporegime", "boss", "don", "godfather",
                    "capo di tutti capi"}


def drug_trade_blockers(state: GameState, rank: bool = True, home_city: bool = True) -> list:
    """Reasons the character can't run a drug-dealing action right now (empty = OK).
    rank: must be a middling rank. home_city: those ranks except Piciotto must be home."""
    reasons = []
    if not state.logged_in:
        reasons.append("Not logged in")
    if state.in_jail:
        reasons.append("In jail")
    if state.in_hospital:
        reasons.append("In hospital")
    r = norm_rank(state.rank)
    if rank and r not in MIDDLING_RANKS:
        reasons.append(f"Rank '{state.rank or 'unknown'}' can't deal drugs")
    if home_city and r in _HOME_CITY_REQUIRED_RANKS and not state.in_home_city():
        reasons.append("Not in home city")
    return reasons


def drug_house_blockers(state: GameState, home_city: bool = True) -> list:
    """Reasons the character can't use the drug house or add a dealer contact (empty = OK)."""
    reasons = []
    if not state.logged_in:
        reasons.append("Not logged in")
    if state.in_jail:
        reasons.append("In jail")
    if state.in_hospital:
        reasons.append("In hospital")
    if norm_rank(state.rank) not in DRUG_HOUSE_RANKS:
        reasons.append(f"Rank '{state.rank or 'unknown'}' can't use the drug house")
    if home_city and not state.in_home_city():
        reasons.append("Not in home city")
    return reasons


_middling_queue: "queue.Queue | None" = None


def set_middling_queue(q: "queue.Queue"):
    global _middling_queue
    _middling_queue = q


# Canonical drug keys (the order the game lists them) and the names a !middle command
# accepts for each. Matching ignores case and spaces, so "P / ICE" and "crystal meth" work.
MIDDLE_DRUGS = {
    "marijuana": ("marijuana", "weed", "mj", "pot", "grass", "ganja", "cannabis", "mary jane"),
    "ecstasy":   ("ecstasy", "ecstacy", "e", "x", "xtc", "mdma", "molly"),
    "acid":      ("acid", "lsd"),
    "speed":     ("speed", "amphetamine", "amphetamines", "amph"),
    "ice":       ("ice", "p/ice", "pice", "p", "meth", "crystal", "crystal meth"),
    "heroin":    ("heroin", "h", "smack", "horse"),
    "cocaine":   ("cocaine", "coke", "c", "blow", "snow", "charlie"),
}


def _alias_key(name: str) -> str:
    return re.sub(r"\s+", "", name).lower()


DRUG_ALIASES = {_alias_key(alias): key
                for key, aliases in MIDDLE_DRUGS.items() for alias in aliases}


def parse_drug_list(text: str):
    """Turn a comma-delimited drug list ("weed,ecstasy,coke") into canonical keys.
    Returns (keys, unknown): keys in the order given with duplicates dropped, and the
    names that matched no drug."""
    keys, unknown = [], []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        key = DRUG_ALIASES.get(_alias_key(part))
        if key is None:
            unknown.append(part)
        elif key not in keys:
            keys.append(key)
    return keys, unknown


def parse_middle_command(text: str):
    """Parse a !middle command from message text: !middle <runner> <buyer> [drugs] [--all].
    drugs is an optional comma-delimited list ("weed,ecstasy,coke"); everything after the
    buyer other than --all is read as that list, so spaces around the commas are fine.
    --all repeats the run (buy, offer, wait for the buyer to accept) until the runner is out.
    Returns None, or {runner, buyer, drugs, unknown, all}: drugs is a list of canonical keys
    (empty = no list given, buy any drug); unknown holds names that matched no drug.
    Only the first line is checked."""
    first_line = text.split("\n", 1)[0].strip()
    m = re.match(r"^!middle\s+(\S+)\s+(\S+)(?:\s+(.+))?$", first_line, re.IGNORECASE)
    if not m:
        return None
    rest = m.group(3) or ""
    all_mode = bool(re.search(r"(?<!\S)--all(?!\S)", rest, re.IGNORECASE))
    rest = re.sub(r"(?<!\S)--all(?!\S)", " ", rest, flags=re.IGNORECASE)
    drugs, unknown = parse_drug_list(rest)
    return {"runner": m.group(1), "buyer": m.group(2), "drugs": drugs,
            "unknown": unknown, "all": all_mode}


def describe_command(item: dict) -> str:
    """The command as the bot understood it, e.g. "!middle Runner Buyer marijuana,cocaine --all"."""
    text = f"!middle {item['runner']} {item['buyer']}"
    if item.get("drugs"):
        text += " " + ",".join(item["drugs"])
    if item.get("all"):
        text += " --all"
    return text


# ---------------------------------------------------------------------------
# Open drug trade offers and the --all run waiting on its buyer
# ---------------------------------------------------------------------------
# Offers the bot has made and not yet seen answered, by buyer (lower case):
# {"buyer", "price", "drugs": {key: qty}, "kind", "at"}. The journal's "Drug Trade Offer
# Accepted" entry turns one into a recorded sale.
_open_offers: dict = {}
# The --all run waiting for its buyer to accept (only one at a time). Its "run" dict is
# the queue item, carried from round to round.
_waiting: "dict | None" = None
_ready: "dict | None" = None
_state_lock = threading.Lock()

_ANSWER_RE = re.compile(
    r"^\s*(\S+)\s+has\s+(accepted|declined|rejected|refused)\s+your\s+drug\s+trade\s+offer"
    r"(?:\s+for\s+\$([\d,]+))?", re.IGNORECASE)


def note_offer(buyer: str, price: int, drugs: dict, kind: str = "offer"):
    """Executor (drug window): an offer to `buyer` went up."""
    with _state_lock:
        _open_offers[buyer.lower()] = {"buyer": buyer, "price": price, "drugs": dict(drugs),
                                       "kind": kind, "at": time.time()}


def wait_for_buyer(run: dict):
    """Executor (drug window): an --all round's offer is up; hold the run until the buyer
    accepts it."""
    global _waiting
    with _state_lock:
        run["waiting_since"] = time.time()
        _waiting = run


def end_run(run: dict):
    global _waiting, _ready
    with _state_lock:
        if _waiting is run:
            _waiting = None
        if _ready is run:
            _ready = None


def waiting_run() -> "dict | None":
    with _state_lock:
        return _waiting


def handle_offer_journal(entry: dict, state: GameState) -> bool:
    """Journal dispatch (bot thread): "<buyer> has accepted your drug trade offer for $X!".
    Records the sale, and lets an --all run waiting on that buyer go again. A decline ends
    the run. Returns True when the entry was a reply to one of our offers."""
    global _waiting, _ready
    m = _ANSWER_RE.match(entry.get("text", "") or "")
    if not m:
        return False
    buyer, verb = m.group(1), m.group(2).lower()
    price = int(m.group(3).replace(",", "")) if m.group(3) else None
    with _state_lock:
        offer = _open_offers.pop(buyer.lower(), None)
        run = _waiting if _waiting and _waiting["buyer"].lower() == buyer.lower() else None
        if run is not None:
            _waiting = None
    import action_log
    drugs = (offer or {}).get("drugs", {})
    amount = price if price is not None else (offer or {}).get("price")
    accepted = verb == "accepted"
    action_log.record(state, "drug_sell", (offer or {}).get("kind", "offer"),
                      "success" if accepted else "fail", target=buyer,
                      amount=amount if accepted else None,
                      message=entry.get("text", ""), drugs=drugs, units=sum(drugs.values()))
    state.add_log(f"Drug trade: {buyer} {verb} our offer"
                  + (f" for ${amount:,}" if amount else "") + ".")
    if run is not None:
        if run.get("rounds"):
            run["rounds"][-1]["accepted"] = accepted
        if accepted:
            with _state_lock:
                _ready = run
        else:
            run["stop_reason"] = f"{buyer} {verb} the offer"
            _notify_run_end(state, run)
    return True


def _money(n) -> str:
    return f"${n:,}"


def run_summary(run: dict) -> str:
    """What a run bought and sold, for the comms reply."""
    rounds = run.get("rounds", [])
    if not rounds:
        return "Nothing was bought."
    lines = []
    total_units = total_cost = 0
    sold_units = sold_cost = 0
    for i, r in enumerate(rounds, 1):
        parts = ", ".join(f"{d['qty']}x {d['name']} @ {_money(d['price'])}" for d in r["drugs"])
        units = sum(d["qty"] for d in r["drugs"])
        total_units += units
        total_cost += r["cost"]
        status = {True: "accepted", False: "not accepted"}.get(r.get("accepted"), "offered")
        if r.get("accepted"):
            sold_units += units
            sold_cost += r["cost"]
        prefix = f"Round {i}: " if len(rounds) > 1 else ""
        lines.append(f"{prefix}{parts} = {_money(r['cost'])} ({status})")
    head = (f"Bought {total_units} drugs from {run['runner']} for {_money(total_cost)} and "
            f"offered them to {run['buyer']} at cost.")
    if run.get("all"):
        head += f" {run['buyer']} accepted {sold_units} for {_money(sold_cost)}."
    return head + "\n" + "\n".join(lines)


def _notify_run_end(state, run: dict):
    """Queue the end-of-run message to whoever sent the command (bot thread)."""
    notify_sender(state, run, finish_run(run))


def finish_run(run: dict) -> str:
    """End a run; returns the message for whoever sent the command."""
    end_run(run)
    reason = run.get("stop_reason")
    cmd = describe_command(run)
    if reason and not run.get("rounds"):
        body = f"{cmd} failed: {reason}."
    elif reason:
        body = f"{cmd} stopped: {reason}.\n{run_summary(run)}"
    else:
        body = f"{cmd} done.\n{run_summary(run)}"
    return body


def notify_sender(state, item: dict, body: str):
    """Reply to the !middle sender in the conversation the command came from (bot thread:
    queued to the drug window, which does the sending)."""
    state.add_log(f"Middling: {body.splitlines()[0]}")
    if not item.get("sender"):
        return
    try:
        import drug_window
        drug_window.submit(state, Action("middle_notify", to=item["sender"],
                                         conv_id=item.get("conv_id", ""), body=body))
    except Exception as e:
        state.add_log(f"Middling: couldn't queue the reply to {item['sender']}: {e}")


def validate_middle_players(runner: str, buyer: str) -> "str | None":
    """Check both runner and buyer are active (alive) players.
    Case-insensitive lookup. Returns an error string or None on success."""
    import player_db
    all_players = player_db.get_all_players()
    active_lower = {p["username"].lower(): p["username"] for p in all_players if p.get("active")}
    missing = []
    if runner.lower() not in active_lower:
        missing.append(runner)
    if buyer.lower() not in active_lower:
        missing.append(buyer)
    if missing:
        return f"player(s) not found in active list: {', '.join(missing)}"
    return None


DEFAULT_ACCEPT_TIMEOUT_MINS = 30


def _accept_timeout_secs() -> int:
    import config as cfg
    mins = cfg.load().get("middling", {}).get("accept_timeout_mins", DEFAULT_ACCEPT_TIMEOUT_MINS)
    return max(1, int(mins or DEFAULT_ACCEPT_TIMEOUT_MINS)) * 60


class MiddlingTask(Task):
    """Runs queued !middle commands. An --all run holds the queue while it waits for its
    buyer to accept; the accept journal (handle_offer_journal) marks it ready for the next
    round, and it gives up after middling.accept_timeout_mins."""
    priority = 90
    label = "Drug Middling"

    def __init__(self, middling_queue: queue.Queue):
        self._queue = middling_queue

    def can_run(self, state: GameState) -> bool:
        return not self.blocked_reasons(state)

    def _timed_out(self) -> "dict | None":
        run = waiting_run()
        if run and time.time() - run.get("waiting_since", time.time()) > _accept_timeout_secs():
            return run
        return None

    def blocked_reasons(self, state):
        import config as cfg
        reasons = []
        if state.drug_tab_active:
            reasons.append("Drug window busy")
        if self._timed_out():
            return reasons  # only needs the drug window to send the "gave up" reply
        reasons += drug_trade_blockers(state)
        if not cfg.load().get("middling", {}).get("enabled", False):
            reasons.append("Middling disabled")
        with _state_lock:
            ready, waiting = _ready, _waiting
        if waiting is not None:
            reasons.append(f"Waiting for {waiting['buyer']} to accept the offer")
        elif ready is None and self._queue.empty():
            reasons.append("Queue empty")
        return reasons

    def run(self, state: GameState, executor):
        global _ready
        run = self._timed_out()
        if run:
            mins = _accept_timeout_secs() // 60
            run["stop_reason"] = f"{run['buyer']} didn't accept the offer within {mins} min"
            _notify_run_end(state, run)
            return
        with _state_lock:
            item, _ready = _ready, None
        if item is None:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
        import drug_window
        drug_window.submit(state, Action("do_middling", run=item))
