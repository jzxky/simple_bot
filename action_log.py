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

import csv
import io
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
    "travel": "Travel",
    "payback": "Payback",
    "consume": "Consume",
    "community_service": "Community service",
    "dog_train": "Dog trains",
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
    _initialized = True


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
                " target, amount, city, message, detail, source)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(r["ts"], r.get("server_time", ""), character, r["category"], r.get("kind", ""),
                  r["result"], r.get("target", ""), r.get("amount"), r.get("city", ""),
                  (r.get("message") or "")[:1000],
                  json.dumps(r["detail"], default=str) if r.get("detail") else "", source)
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
    """Build a WHERE clause from a filter dict (all keys optional):
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
    sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return sql, args


def _read(fn):
    with _lock:
        _ensure()
    with _conn() as c:
        return fn(c)


def query(f: dict, page: int = 1, per_page: int = 100) -> dict:
    where, args = _where(f)
    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 100), 1000))

    def run(c):
        total = c.execute(f"SELECT COUNT(*) FROM actions{where}", args).fetchone()[0]
        rows = c.execute(
            f"SELECT * FROM actions{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            args + [per_page, (page - 1) * per_page],
        ).fetchall()
        return {"total": total, "page": page, "per_page": per_page,
                "rows": [_row(r) for r in rows]}
    return _read(run)


def _row(r) -> dict:
    d = dict(r)
    try:
        d["detail"] = json.loads(d["detail"]) if d.get("detail") else {}
    except Exception:
        d["detail"] = {"raw": d.get("detail")}
    return d


def summary(f: dict) -> dict:
    """Totals, a daily success/fail series and per-category breakdowns for a filter."""
    where, args = _where(f)
    and_ = " AND " if where else " WHERE "

    def run(c):
        t = c.execute(
            "SELECT COUNT(*) n,"
            " SUM(result='success') s, SUM(result='fail') fl,"
            " COALESCE(SUM(CASE WHEN result='success' THEN amount END),0) amt"
            f" FROM actions{where}", args).fetchone()
        n, s, fl, amt = t["n"] or 0, t["s"] or 0, t["fl"] or 0, t["amt"] or 0
        daily = [dict(r) for r in c.execute(
            "SELECT substr(ts,1,10) day, SUM(result='success') success, SUM(result='fail') fail"
            f" FROM actions{where} GROUP BY day ORDER BY day DESC LIMIT 60", args)][::-1]
        by_kind = [dict(r) for r in c.execute(
            "SELECT category, kind, COUNT(*) n, SUM(result='success') success,"
            " SUM(result='fail') fail,"
            " COALESCE(SUM(CASE WHEN result='success' THEN amount END),0) amount"
            f" FROM actions{where} GROUP BY category, kind ORDER BY n DESC LIMIT 50", args)]
        top_targets = [dict(r) for r in c.execute(
            "SELECT target, COUNT(*) n, SUM(result='success') success,"
            " COALESCE(SUM(CASE WHEN result='success' THEN amount END),0) amount"
            f" FROM actions{where}{and_}target != '' GROUP BY target"
            " ORDER BY amount DESC, n DESC LIMIT 10", args)]
        fail_reasons = [dict(r) for r in c.execute(
            "SELECT message, COUNT(*) n"
            f" FROM actions{where}{and_}result = 'fail' AND message != ''"
            " GROUP BY message ORDER BY n DESC LIMIT 10", args)]
        return {
            "attempts": n, "success": s, "fail": fl,
            "success_rate": round(100.0 * s / (s + fl), 1) if (s + fl) else None,
            "amount": amt, "per_success": int(amt / s) if s else 0,
            "daily": daily, "by_kind": by_kind,
            "top_targets": top_targets, "fail_reasons": fail_reasons,
        }
    return _read(run)


def facets(character: str = "") -> dict:
    """Distinct categories/kinds/cities present, for filter dropdowns."""
    where, args = _where({"character": character})

    def run(c):
        kinds = {}
        for r in c.execute(f"SELECT DISTINCT category, kind FROM actions{where}", args):
            kinds.setdefault(r["category"], []).append(r["kind"])
        cities = [r[0] for r in c.execute(
            f"SELECT DISTINCT city FROM actions{where} ORDER BY city", args) if r[0]]
        return {"kinds": {k: sorted(v) for k, v in kinds.items()}, "cities": cities}
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
                    " COALESCE(SUM(CASE WHEN result='success' THEN amount END),0) amount"
                    " FROM actions WHERE character=? GROUP BY category", (d["name"],)):
                totals[t["category"]] = {"n": t["n"], "success": t["success"] or 0,
                                         "fail": t["fail"] or 0, "amount": t["amount"] or 0}
            d["totals"] = totals
            d["actions"] = sum(v["n"] for v in totals.values())
            out.append(d)
        return out
    return _read(run)


CSV_COLUMNS = ["ts", "server_time", "character", "category", "kind", "result",
               "target", "amount", "city", "message", "detail", "source"]


def export_csv(f: dict) -> str:
    where, args = _where(f)

    def run(c):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(CSV_COLUMNS)
        for r in c.execute(f"SELECT {', '.join(CSV_COLUMNS)} FROM actions{where} ORDER BY id DESC", args):
            w.writerow([r[k] if r[k] is not None else "" for k in CSV_COLUMNS])
        return buf.getvalue()
    return _read(run)
