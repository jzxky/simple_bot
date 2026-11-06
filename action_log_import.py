"""
action_log_import.py — rebuild action history from the bot's activity log files.

Each log file (data_dir/logs/YYYY-MM-DD_HH-MM-SS.log) holds the lines the bot
wrote with state.add_log, as "[HH:MM:SS] message" in game time. The lines have
no character name, so the user names the character when importing.

Timestamps: the file name is the local time the bot started; the first line's
game time anchors the offset, and later lines count forward from it (rolling
over at midnight). The result is converted to UTC like live rows.

Lines from the moment the character's live recording started are skipped, so
importing a log that overlaps live history doesn't double-count.
"""

import os
import re
from datetime import datetime, timedelta, timezone

import action_log
import paths

_LINE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\]\s?(.*)$")
_FILE_TS = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})\.log$")


def logs_dir() -> str:
    return os.path.join(paths.data_dir(), "logs")


def list_logs() -> list:
    """Every log file, newest first, with size and import status."""
    d = logs_dir()
    try:
        names = sorted((f for f in os.listdir(d) if f.endswith(".log")), reverse=True)
    except FileNotFoundError:
        return []
    imported = action_log.imported_files()
    out = []
    for name in names:
        try:
            size = os.path.getsize(os.path.join(d, name))
        except OSError:
            size = 0
        out.append({"file": name, "size": size, "imported": imported.get(name, [])})
    return out


def _fail_result(msg: str) -> str:
    return "fail" if "failed" in (msg or "").lower() else "skip"


def _ok(category, kind, msg, target="", **detail):
    return {"category": category, "kind": kind, "result": "success", "target": target,
            "amount": action_log.parse_amount(msg), "message": msg, "detail": detail}


def _bad(category, kind, msg, target="", result="fail", **detail):
    return {"category": category, "kind": kind, "result": result, "target": target,
            "amount": None, "message": msg, "detail": detail}


def _expand_fail_summary(kind: str, text: str) -> list:
    """'3 fails — 2x You failed, 1x recently survived (fail count: 1/3)' → rows."""
    body = re.sub(r"\s*\(fail count:.*\)\s*$", "", text)
    body = body.split("—", 1)[1] if "—" in body else body
    rows = []
    for m in re.finditer(r"(\d+)x (.*?)(?=, \d+x |$)", body.strip()):
        msg = m.group(2).strip()
        if _fail_result(msg) != "fail":
            continue  # recently survived, increased security… aren't real attempts
        for _ in range(int(m.group(1))):
            rows.append(_bad("agg", kind, msg, summarised=True))
    return rows


class _Parser:
    """Turns one log's messages into action rows. Keeps a little context
    between lines (the selected crime, the hospital case being worked…)."""

    def __init__(self):
        self.crime = ""
        self.hospital_injury = ""
        self.fire_target = ""
        self.eng_job = ""
        self.eng_target = ""
        self.cs = None  # (category, service, where) for the next result line

    def parse(self, msg: str) -> list:
        if msg.startswith("[Side] "):
            msg = msg[len("[Side] "):]
        m = re.match(r"Selected crime: (\w+)", msg)
        if m:
            self.crime = m.group(1)
            return []

        # ── Agg crimes ────────────────────────────────────────────────────
        m = re.match(r"Crime success vs (.+?)(?: \(retry\))?: (.*)$", msg)
        if m:
            return [_ok("agg", self.crime or "unknown", m.group(2), m.group(1))]
        m = re.match(r"B&E success vs (.+?): (.*)$", msg)
        if m:
            return [_ok("agg", "breaking", m.group(2), m.group(1))]
        m = re.match(r"Crime run: (.*)$", msg)
        if m:
            return _expand_fail_summary(self.crime or "unknown", m.group(1))
        m = re.match(r"B&E run: (.*)$", msg)
        if m:
            return _expand_fail_summary("breaking", m.group(1))
        m = re.match(r"(Armed robbery|Torch business) success \((.+?)\): (.*)$", msg)
        if m:
            kind = "armed" if m.group(1) == "Armed robbery" else "torch"
            return [_ok("agg", kind, m.group(3), m.group(2))]
        m = re.match(r"(Armed robbery|Torch business) failed: (.*)$", msg)
        if m:
            kind = "armed" if m.group(1) == "Armed robbery" else "torch"
            if _fail_result(m.group(2)) != "fail":
                return []
            return [_bad("agg", kind, m.group(2))]

        # ── Case work ─────────────────────────────────────────────────────
        m = re.match(r"Hospital case work result: (.*)$", msg)
        if m:
            return [_ok("case_work", "hospital", m.group(1), injury=self.hospital_injury)]
        m = re.match(r"Hospital case work failed: (.*)$", msg)
        if m:
            return [_bad("case_work", "hospital", m.group(1), injury=self.hospital_injury)]
        if msg == "Hospital case work: submitted.":
            return [_ok("case_work", "hospital", "Submitted (no result message)",
                        injury=self.hospital_injury)]
        m = re.match(r"Hospital case work: (.*)\.$", msg)
        if m:
            self.hospital_injury = m.group(1)
            return []

        m = re.match(r"Fire case work: attending fire for (.+)\.$", msg)
        if m:
            self.fire_target = m.group(1)
            return []
        m = re.match(r"Fire (case work|investigation|inspection) (result|failed): (.*)$", msg)
        if m:
            job = {"case work": "fire"}.get(m.group(1), m.group(1))
            target = self.fire_target if job == "fire" else ""
            row = (_ok if m.group(2) == "result" else _bad)("case_work", "fire", m.group(3), target, job=job)
            return [row]

        m = re.match(r"Engineering: (.+?)(?: for '(.+)')?\.$", msg)
        if m:
            self.eng_job, self.eng_target = m.group(1), m.group(2) or ""
            return []
        m = re.match(r"Engineering (result|failed): (.*)$", msg)
        if m:
            fn = _ok if m.group(1) == "result" else _bad
            return [fn("case_work", "engineering", m.group(2), self.eng_target, job=self.eng_job)]

        m = re.match(r"Lawyer: defended case #(\S+) \((.*?)\) for (.+?) — (.*)$", msg)
        if m:
            return [_ok("case_work", "lawyer", m.group(4), m.group(3), case_id=m.group(1), crime=m.group(2))]
        m = re.match(r"Lawyer: defended case #(\S+) after transfer — (.*)$", msg)
        if m:
            return [_ok("case_work", "lawyer", m.group(2), case_id=m.group(1), retry=True)]
        m = re.match(r"Lawyer: case #(\S+) failed — (.*)$", msg)
        if m:
            return [_bad("case_work", "lawyer", m.group(2), case_id=m.group(1))]

        m = re.match(r"Banking (.+?): transfer failed — (.*)$", msg)
        if m:
            return [_bad("case_work", "banking", m.group(2), m.group(1))]
        m = re.match(r"Banking (.+?): launder produced no transfer \((.*)\)\.$", msg)
        if m:
            return [_bad("case_work", "banking", m.group(2), m.group(1))]
        m = re.match(r"Banking ([^:]+): (.*\$[\d,]+.*)$", msg)
        if m and not m.group(2).startswith(("error", "launder form", "transfer submitted")):
            return [_ok("case_work", "banking", m.group(2), m.group(1))]

        # ── Earns ─────────────────────────────────────────────────────────
        m = re.match(r"Manual earn \((.+?)\) failed: (.+?) — (.*)$", msg)
        if m:
            return [_bad("earn", m.group(2), m.group(3), how=m.group(1))]
        m = re.match(r"Manual earn \((.+?)\): (.+?) — (.*)$", msg)
        if m and not m.group(3).startswith("no result message"):
            return [_ok("earn", m.group(2), m.group(3), how=m.group(1))]
        m = re.match(r"Earn queue: added (\d+) x (.+)\.$", msg)
        if m:
            row = _ok("earn_queue", m.group(2), f"Queued {m.group(1)} x {m.group(2)}",
                      queued=int(m.group(1)))
            row["amount"] = None
            return [row]

        # ── Community service / dog trains ────────────────────────────────
        m = re.match(r"Community service \((home|away) city\): (.+)$", msg)
        if m:
            self.cs = ("community_service", m.group(2), m.group(1))
            return []
        # A result line follows its option line; any other dog-trains line is the option.
        m = re.match(r"(Community service|Dog trains): (failed — )?(.*)$", msg)
        if m and self.cs and self.cs[0] == ("dog_train" if m.group(1) == "Dog trains" else "community_service"):
            cat, service, where = self.cs
            self.cs = None
            fn = _bad if m.group(2) else _ok
            row = fn(cat, service, m.group(3), where=where)
            row["amount"] = None
            return [row]
        m = re.match(r"Dog trains: (?!no dog|couldn't|away action|actions disabled|failed — )(.+)$", msg)
        if m:
            self.cs = ("dog_train", m.group(1), "")
            return []

        # ── Gym ───────────────────────────────────────────────────────────
        m = re.match(r"Gym: completed activity '(.+)'\.$", msg)
        if m:
            return [_ok("gym", m.group(1), "Completed")]
        m = re.match(r"Gym: purchased membership \(\$([\d,]+)\)\.$", msg)
        if m:
            row = _ok("gym", "membership", msg)
            row["amount"] = -int(m.group(1).replace(",", ""))
            return [row]
        if msg.startswith("Gym: travel to Chicago failed") or msg.startswith("Gym: still insufficient funds"):
            return [_bad("gym", "", msg[len("Gym: "):])]

        # ── Jail ──────────────────────────────────────────────────────────
        m = re.match(r"Jail duty \((.+?)\) failed: (.*)$", msg)
        if m:
            return [_bad("jail_duty", m.group(1), m.group(2))]
        m = re.match(r"Jail duty \((.+?)\): (.*)$", msg)
        if m:
            text = m.group(2)
            return [_ok("jail_duty", m.group(1),
                        "Submitted (no result message)" if text == "submitted." else text)]
        m = re.match(r"Jail action \((.+?)\) failed: (.*)$", msg)
        if m:
            return [_bad("jail", m.group(1), m.group(2))]
        m = re.match(r"Jail action \((.+?)\): (.*)$", msg)
        if m:
            return [_ok("jail", m.group(1), m.group(2))]
        m = re.match(r"Jail break executed: (.*)$", msg)
        if m:
            fn = _bad if "fail" in m.group(1).lower() else _ok
            return [fn("jail", "jailbreak", m.group(1))]

        # ── Travel ────────────────────────────────────────────────────────
        m = re.match(r"Travel: departing to (.+) by vehicle\.$", msg)
        if m:
            return [_ok("travel", "own_vehicle", msg, m.group(1))]
        m = re.match(r"Travel: flight to (.+) booked", msg)
        if m:
            return [_ok("travel", "airport", msg, m.group(1))]

        # ── Payback / consume ─────────────────────────────────────────────
        m = re.match(r"Payback sent: \$([\d,]+) to (.+)\.$", msg)
        if m:
            row = _ok("payback", "transfer", msg, m.group(2))
            row["amount"] = int(m.group(1).replace(",", ""))
            return [row]
        m = re.match(r"Payback to (.+) blocked as spam", msg)
        if m:
            return [_bad("payback", "transfer", "Transfer blocked as spam", m.group(1))]
        m = re.match(r"Consume (.+?): (.*)$", msg)
        if m:
            text = m.group(2)
            ok = "success" in text.lower() and not text.lower().startswith("you successfully used 0")
            row = (_ok if ok else _bad)("consume", m.group(1), text)
            row["amount"] = None
            return [row]
        return []


def _file_start(filename: str) -> "datetime | None":
    m = _FILE_TS.match(filename)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}:{m.group(3)}:{m.group(4)}",
                                 "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def parse_file(path: str, filename: str) -> list:
    """Parse one log file into rows ready for action_log.replace_imported()."""
    start = _file_start(filename)
    if start is None:
        start = datetime.fromtimestamp(os.path.getmtime(path))
    start_utc = start.astimezone(timezone.utc)  # naive local → aware UTC
    parser = _Parser()
    rows = []
    first_secs = None
    day = 0
    prev = None
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = _LINE.match(line.rstrip("\n"))
            if not m:
                continue
            secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            if first_secs is None:
                first_secs = secs
            if prev is not None and secs < prev - 3600:  # game clock passed midnight
                day += 1
            prev = secs
            offset = day * 86400 + secs - first_secs
            ts = (start_utc + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")
            server_time = f"{m.group(1)}:{m.group(2)}:{m.group(3)}"
            for row in parser.parse(m.group(4)):
                row["ts"] = ts
                row["server_time"] = server_time
                rows.append(row)
    return rows


def run_import(files: list, character: str, dry_run: bool = False) -> dict:
    """Import (or preview) the chosen log files as `character`."""
    character = (character or "").strip()
    if not character:
        raise ValueError("Enter the character name these logs belong to.")
    cutoff = action_log.live_start(character)
    d = logs_dir()
    results = []
    for name in files:
        safe = os.path.basename(name)
        path = os.path.join(d, safe)
        if not safe.endswith(".log") or not os.path.isfile(path):
            results.append({"file": safe, "error": "not found"})
            continue
        rows = parse_file(path, safe)
        skipped = 0
        if cutoff:
            kept = [r for r in rows if r["ts"] < cutoff]
            skipped = len(rows) - len(kept)
            rows = kept
        by_cat = {}
        for r in rows:
            by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
        if not dry_run:
            action_log.replace_imported(character, safe, rows)
        results.append({"file": safe, "rows": len(rows), "skipped_live": skipped,
                        "by_category": by_cat})
    return {"character": character, "dry_run": dry_run, "files": results,
            "total": sum(r.get("rows", 0) for r in results)}
