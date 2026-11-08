"""
action_log.py — SQLite-backed history of every action the bot takes.

Tables (data_dir/actions.db, gitignored via *.db):
  actions    — one row per action, always tied to the character that did it
  characters — one row per character the bot has ever played

Every write goes through record(). It never raises: a logging problem must
never stop a task. Rows are only written when the logged-in character's name
(state.own_name) is known, so a new character's history never mixes with an
old one's.
"""

import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

import paths

DB_PATH = os.path.join(paths.data_dir(), "actions.db")

_lock = threading.Lock()
_initialized = False

RESULTS = ("success", "fail", "skip", "error")

CATEGORY_LABELS = {
    "agg": "Agg crimes",
    "case_work": "Case work",
    "earn": "Earns",
    "earn_queue": "Earn queue",
    "gym": "Gym",
    "jail": "Jail",
    "consume": "Consume",
    "community_service": "Community service",
    "dog_train": "Dog trains",
    "jail_duty": "Jail duties",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    server_time TEXT DEFAULT '',
    character   TEXT NOT NULL,
    category    TEXT NOT NULL,
    kind        TEXT DEFAULT '',
    result      TEXT NOT NULL,
    target      TEXT DEFAULT '',
    amount      INTEGER,
    city        TEXT DEFAULT '',
    message     TEXT DEFAULT '',
    detail      TEXT DEFAULT '',
    source      TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS characters (
    name        TEXT PRIMARY KEY,
    first_seen  TEXT NOT NULL,
    last_seen   TEXT NOT NULL,
    home_city   TEXT DEFAULT '',
    occupation  TEXT DEFAULT '',
    rank        TEXT DEFAULT '',
    status      TEXT DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_actions_char_ts ON actions(character, ts);
CREATE INDEX IF NOT EXISTS idx_actions_cat ON actions(category, kind, ts);
CREATE INDEX IF NOT EXISTS idx_actions_target ON actions(target);
"""

# Columns added after the first release — applied via ALTER TABLE if missing.
# source: '' for rows the bot recorded live, 'import:<log file>' for rows
# imported from an activity log.
_MIGRATIONS = [
    ("actions", "source", "TEXT DEFAULT ''"),
    # paid_back: payback sent for this agg (paybacks belong to the agg they
    # repay rather than being separate actions).
    ("actions", "paid_back", "INTEGER"),
]


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def _ensure():
    global _initialized
    if _initialized:
        return
    with _conn() as c:
        c.executescript(_SCHEMA)
        for table, col, decl in _MIGRATIONS:
            cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        c.execute("CREATE INDEX IF NOT EXISTS idx_actions_source ON actions(character, source)")
        # Travel is no longer tracked; clear rows recorded before that change.
        c.execute("DELETE FROM actions WHERE category = 'travel'")
        _fold_paybacks(c)
    _initialized = True


# The agg a payback repays: the latest successful agg on that target (or the
# business owner, for torches and armed robberies) not already paid back.
_AGG_FOR_PAYBACK = (
    "SELECT id FROM actions WHERE character=? AND category='agg' AND result='success'"
    " AND paid_back IS NULL AND ts <= ?"
    " AND (lower(target)=lower(?) OR (detail != '' AND lower(json_extract(detail, '$.owner'))=lower(?)))"
    " ORDER BY ts DESC, id DESC LIMIT 1")


def _fold_paybacks(c):
    """Older versions stored paybacks as their own 'payback' rows. Move each
    successful one onto the agg it repaid, then drop the payback rows."""
    rows = c.execute("SELECT id, ts, character, target, amount, result FROM actions"
                     " WHERE category='payback' ORDER BY ts, id").fetchall()
    for r in rows:
        if r["result"] == "success" and r["amount"]:
            agg = c.execute(_AGG_FOR_PAYBACK, (r["character"], r["ts"], r["target"], r["target"])).fetchone()
            if agg:
                c.execute("UPDATE actions SET paid_back=? WHERE id=?", (r["amount"], agg["id"]))
    if rows:
        c.execute("DELETE FROM actions WHERE category='payback'")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_amount(text: str) -> "int | None":
    """First $1,234 figure in a game message, or None."""
    m = re.search(r"\$([\d,]+)", text or "")
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def record(state, category: str, kind: str, result: str, target: str = "",
           amount: "int | None" = None, message: str = "", **detail):
    """Record one action for the character currently logged in.

    Dropped silently when the character name isn't known yet (before login)."""
    try:
        character = (getattr(state, "own_name", "") or "").strip()
        if not character:
            return
        if result not in RESULTS:
            result = "success" if result is True else "fail" if result is False else str(result)
        st = getattr(state, "server_time", None)
        server_time = st.strftime("%H:%M:%S") if st else ""
        ts = _now()
        detail_json = json.dumps(detail, default=str) if detail else ""
        with _lock:
            _ensure()
            with _conn() as c:
                c.execute(
                    "INSERT INTO actions (ts, server_time, character, category, kind, result,"
                    " target, amount, city, message, detail)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (ts, server_time, character, category, kind or "", result,
                     target or "", amount, getattr(state, "current_city", "") or "",
                     (message or "")[:1000], detail_json),
                )
                c.execute(
                    "INSERT INTO characters (name, first_seen, last_seen, home_city, occupation, rank)"
                    " VALUES (?,?,?,?,?,?)"
                    " ON CONFLICT(name) DO UPDATE SET last_seen=excluded.last_seen,"
                    " home_city=COALESCE(NULLIF(excluded.home_city,''), characters.home_city),"
                    " occupation=COALESCE(NULLIF(excluded.occupation,''), characters.occupation),"
                    " rank=COALESCE(NULLIF(excluded.rank,''), characters.rank)",
                    (character, ts, ts, getattr(state, "home_city", "") or "",
                     getattr(state, "occupation", "") or "", getattr(state, "rank", "") or ""),
                )
    except Exception as e:
        print(f"[action_log] record failed: {e}")


def record_payback(state, target: str, amount: int):
    """Note a payback on the agg it repays (latest successful agg on `target`,
    the victim or business owner, that hasn't been paid back yet)."""
    try:
        character = (getattr(state, "own_name", "") or "").strip()
        if not character or not amount:
            return
        with _lock:
            _ensure()
            with _conn() as c:
                agg = c.execute(_AGG_FOR_PAYBACK, (character, _now(), target, target)).fetchone()
                if agg:
                    c.execute("UPDATE actions SET paid_back=? WHERE id=?", (int(amount), agg["id"]))
    except Exception as e:
        print(f"[action_log] record_payback failed: {e}")


def set_character_status(name: str, status: str):
    """Mark a character as e.g. 'quit' or 'dead'. No-op for unknown names."""
    if not name:
        return
    try:
        with _lock:
            _ensure()
            with _conn() as c:
                c.execute("UPDATE characters SET status=? WHERE name=?", (status, name))
    except Exception as e:
        print(f"[action_log] set_character_status failed: {e}")


# ---------------------------------------------------------------------------
# Importing from activity logs
# ---------------------------------------------------------------------------

def import_source(filename: str) -> str:
    return f"import:{filename}"


def live_start(character: str) -> "str | None":
    """Timestamp of the character's first live (not imported) row, or None.
    Log lines from then on are already in the database, so imports skip them."""
    def run(c):
        r = c.execute("SELECT MIN(ts) FROM actions WHERE character=? AND source=''",
                      (character,)).fetchone()
        return r[0] if r else None
    return _read(run)


def imported_files() -> dict:
    """{log filename: [{"character": name, "rows": n}, ...]} for every imported log."""
    def run(c):
        out = {}
        for r in c.execute("SELECT source, character, COUNT(*) n FROM actions"
                           " WHERE source LIKE 'import:%' GROUP BY source, character"):
            out.setdefault(r["source"][len("import:"):], []).append(
                {"character": r["character"], "rows": r["n"]})
        return out
    return _read(run)


def replace_imported(character: str, filename: str, rows: list) -> int:
    """Store rows parsed from one log file for `character`, replacing anything
    previously imported from that file for any character. Returns rows written."""
    character = (character or "").strip()
    if not character:
        raise ValueError("character name is required")
    source = import_source(filename)
    with _lock:
        _ensure()
        with _conn() as c:
            c.execute("DELETE FROM actions WHERE source=?", (source,))
            c.executemany(
                "INSERT INTO actions (ts, server_time, character, category, kind, result,"
                " target, amount, city, message, detail, source, paid_back)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(r["ts"], r.get("server_time", ""), character, r["category"], r.get("kind", ""),
                  r["result"], r.get("target", ""), r.get("amount"), r.get("city", ""),
                  (r.get("message") or "")[:1000],
                  json.dumps(r["detail"], default=str) if r.get("detail") else "", source,
                  r.get("paid_back"))
                 for r in rows],
            )
            if rows:
                first = min(r["ts"] for r in rows)
                last = max(r["ts"] for r in rows)
                c.execute(
                    "INSERT INTO characters (name, first_seen, last_seen) VALUES (?,?,?)"
                    " ON CONFLICT(name) DO UPDATE SET"
                    " first_seen=MIN(characters.first_seen, excluded.first_seen),"
                    " last_seen=MAX(characters.last_seen, excluded.last_seen)",
                    (character, first, last),
                )
    return len(rows)


# ---------------------------------------------------------------------------
# Reading (viewer)
# ---------------------------------------------------------------------------

_RANGES = {"24h": 1, "7d": 7, "30d": 30}


def _where(f: dict):
    """(" WHERE ...", args) for a filter dict, or ("", []) with no filters."""
    body, args = _conditions(f)
    return ((" WHERE " + body) if body else ""), args


def _conditions(f: dict):
    """Build the conditions from a filter dict (all keys optional):
    character, category, kind, result, city, q, range (today|24h|7d|30d|all),
    since, until (YYYY-MM-DD)."""
    clauses, args = [], []
    for key in ("character", "category", "kind", "result", "city"):
        val = (f.get(key) or "").strip()
        if val:
            clauses.append(f"{key} = ?")
            args.append(val)
    q = (f.get("q") or "").strip()
    if q:
        clauses.append("(target LIKE ? OR message LIKE ?)")
        args += [f"%{q}%", f"%{q}%"]
    rng = (f.get("range") or "").strip()
    now = datetime.now(timezone.utc)
    if rng == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        clauses.append("ts >= ?")
        args.append(start.strftime("%Y-%m-%dT%H:%M:%SZ"))
    elif rng in _RANGES:
        clauses.append("ts >= ?")
        args.append((now - timedelta(days=_RANGES[rng])).strftime("%Y-%m-%dT%H:%M:%SZ"))
    since = (f.get("since") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", since):
        clauses.append("ts >= ?")
        args.append(since + "T00:00:00Z")
    until = (f.get("until") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", until):
        clauses.append("ts <= ?")
        args.append(until + "T23:59:59Z")
    return " AND ".join(clauses), args


def _read(fn):
    with _lock:
        _ensure()
    with _conn() as c:
        return fn(c)


def _row(r) -> dict:
    d = dict(r)
    try:
        d["detail"] = json.loads(d["detail"]) if d.get("detail") else {}
    except Exception:
        d["detail"] = {"raw": d.get("detail")}
    return d


# Amount shown per type: what was taken or earned.
_AMOUNT = "CASE WHEN result='success' AND amount > 0 THEN amount END"
# Consumables used: the item count recorded with each consume (1 when not recorded).
_UNITS = ("CASE WHEN category='consume' AND result='success' THEN"
          " COALESCE(CASE WHEN detail != '' THEN json_extract(detail, '$.consumed') END, 1) END")


def summary(f: dict) -> dict:
    """Per category and type counts for the character history summary."""
    where, args = _where(f)

    def run(c):
        by_kind = [dict(r) for r in c.execute(
            "SELECT category, kind, COUNT(*) n, SUM(result='success') success,"
            " SUM(result='fail') fail,"
            f" COALESCE(SUM({_AMOUNT}),0) amount, COALESCE(SUM({_UNITS}),0) units,"
            " COALESCE(SUM(paid_back),0) paid_back"
            f" FROM actions{where} GROUP BY category, kind ORDER BY n DESC", args)]
        and_ = " AND " if where else " WHERE "
        # Successful case work by type: the hospital/fire/engineering job, the
        # lawyer case's crime, and for banking whose money it was (own or a client's).
        case_types = {}
        for r in c.execute(
                "SELECT kind, CASE"
                "  WHEN kind='banking' THEN CASE WHEN lower(target)=lower(character) THEN 'own' ELSE 'client' END"
                "  WHEN kind='lawyer' THEN json_extract(detail, '$.crime')"
                "  ELSE json_extract(detail, '$.job') END t,"
                f" COUNT(*) n, COALESCE(SUM({_AMOUNT}),0) amount"
                f" FROM actions{where}{and_}category='case_work' AND result='success'"
                " AND (detail != '' OR kind='banking') GROUP BY kind, t", args):
            # "repair business #12" and "repair business #40" are one type.
            t = re.sub(r"\s*#\d+$", "", str(r["t"] or "")).strip() or "other"
            key = (r["kind"], t)
            cur = case_types.setdefault(key, {"kind": r["kind"], "type": t, "n": 0, "amount": 0})
            cur["n"] += r["n"]
            cur["amount"] += r["amount"]
        # Why medical work failed: the game's fail messages, most common first.
        hospital_fails = [dict(r) for r in c.execute(
            "SELECT message, COUNT(*) n"
            f" FROM actions{where}{and_}category='case_work' AND kind='hospital' AND result='fail'"
            " GROUP BY message ORDER BY n DESC LIMIT 20", args)]
        return {"by_kind": by_kind,
                "case_types": sorted(case_types.values(), key=lambda x: -x["n"]),
                "hospital_fails": hospital_fails}
    return _read(run)


TABLE_COLUMNS = ["ts", "server_time", "character", "category", "kind", "result",
                 "target", "amount", "paid_back", "city", "message", "source"]
TABLE_FILTERABLE = ["character", "category", "kind", "result", "target", "city", "source"]


def table(f: dict, args) -> dict:
    """Rows (or one column's facet) for the all-actions table.

    `f` scopes it (character and date range); `args` carries the table_query
    contract the DataTable sends: f.<col>, sort, search, page, facet."""
    import table_query
    base, base_args = _conditions(f)

    def run(c):
        out, err = table_query.paged_query(
            c, "actions", args, TABLE_COLUMNS, filterable=TABLE_FILTERABLE,
            search_cols=("target", "message", "kind"), default_sort=[("ts", "DESC")],
            tiebreak="id", per_page_max=500, base_where=base or "1=1", base_params=base_args)
        if err:
            return err
        if "rows" in out:
            out["rows"] = [_row(r) for r in out["rows"]]
        return out
    return _read(run)


def earn_ledger(character: str) -> list:
    """Earn rows for one character, grouped for the earn planner's counts:
    [{category, kind, result, earn_id, queued, cleared, n}] over the 'earn'
    (manual earns) and 'earn_queue' (top-ups = success, clears = skip) rows."""
    def run(c):
        return [dict(r) for r in c.execute(
            "SELECT category, kind, result,"
            " CASE WHEN detail != '' THEN json_extract(detail, '$.earn_id') END earn_id,"
            " COALESCE(SUM(CASE WHEN detail != '' THEN json_extract(detail, '$.queued') END),0) queued,"
            " COALESCE(SUM(CASE WHEN detail != '' THEN json_extract(detail, '$.cleared') END),0) cleared,"
            " COUNT(*) n FROM actions WHERE character=? AND category IN ('earn','earn_queue')"
            " GROUP BY category, kind, result, earn_id", (character,))]
    return _read(run)


def characters() -> list:
    """Every character, newest first, with lifetime totals."""
    def run(c):
        out = []
        for r in c.execute("SELECT * FROM characters ORDER BY last_seen DESC"):
            d = dict(r)
            totals = {}
            for t in c.execute(
                    "SELECT category, COUNT(*) n, SUM(result='success') success,"
                    " SUM(result='fail') fail,"
                    f" COALESCE(SUM({_AMOUNT}),0) amount, COALESCE(SUM({_UNITS}),0) units"
                    " FROM actions WHERE character=? GROUP BY category", (d["name"],)):
                totals[t["category"]] = {"n": t["n"], "success": t["success"] or 0,
                                         "fail": t["fail"] or 0, "amount": t["amount"] or 0,
                                         "units": t["units"] or 0}
            d["totals"] = totals
            d["actions"] = sum(v["n"] for v in totals.values())
            out.append(d)
        return out
    return _read(run)
