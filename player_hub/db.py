"""
Database layer — SQLite with WAL mode for concurrent access.
"""

import os
import sqlite3
from datetime import datetime, timezone

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "player_hub.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TEXT NOT NULL,
    last_login_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS players (
    username               TEXT PRIMARY KEY,
    homecity               TEXT DEFAULT '',
    occupation             TEXT DEFAULT '',
    rank                   TEXT DEFAULT '',
    active                 INTEGER DEFAULT 1,
    group_name             TEXT DEFAULT '',
    agg_crimes             TEXT DEFAULT '',
    case_work              TEXT DEFAULT '',
    character_age          INTEGER DEFAULT 0,
    jail_age               INTEGER DEFAULT 0,
    assignments_updated_at TEXT DEFAULT '',
    scraped_at             TEXT DEFAULT '',
    died_at                TEXT DEFAULT '',
    born_at                TEXT DEFAULT '',
    pic_url                TEXT DEFAULT '',
    monitoring             INTEGER DEFAULT 0,
    sex                    TEXT DEFAULT '',
    wealth                 TEXT DEFAULT '',
    scripting              TEXT DEFAULT '',
    godfather              TEXT DEFAULT '',
    crew_name              TEXT DEFAULT '',
    capos                  TEXT DEFAULT '',
    alias                  TEXT DEFAULT '',
    notes                  TEXT DEFAULT '',
    respect                TEXT DEFAULT '',
    respect_last_checked   REAL DEFAULT 0,
    source_client          TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS career_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    ts         TEXT NOT NULL,
    rank       TEXT DEFAULT '',
    occupation TEXT DEFAULT '',
    homecity   TEXT DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_career_unique
    ON career_history(username, ts, rank, occupation, homecity);
CREATE INDEX IF NOT EXISTS idx_career_username ON career_history(username);

CREATE TABLE IF NOT EXISTS groups (
    name       TEXT PRIMARY KEY,
    color      TEXT DEFAULT '#3498db',
    type       TEXT DEFAULT 'neutral',
    agg_crimes TEXT DEFAULT '',
    case_work  TEXT DEFAULT '',
    updated_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS clients (
    client_id    TEXT PRIMARY KEY,
    label        TEXT DEFAULT '',
    api_key_hash TEXT NOT NULL,
    last_push_at TEXT DEFAULT '',
    last_pull_at TEXT DEFAULT '',
    player_count INTEGER DEFAULT 0,
    created_at   TEXT NOT NULL,
    active       INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS sync_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    client_id     TEXT DEFAULT '',
    action        TEXT NOT NULL,
    player_count  INTEGER DEFAULT 0,
    group_count   INTEGER DEFAULT 0,
    career_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS war_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    side            TEXT NOT NULL CHECK(side IN ('opps','friendlies')),
    ws              INTEGER DEFAULT 0,
    whack_type      TEXT DEFAULT 'Normal',
    last_whack_time TEXT DEFAULT '',
    last_checked    TEXT DEFAULT '',
    source_client   TEXT DEFAULT '',
    updated_at      TEXT DEFAULT '',
    UNIQUE(name, side)
);

CREATE TABLE IF NOT EXISTS war_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    message       TEXT NOT NULL,
    source_client TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_EPOCH = "1970-01-01T00:00:00Z"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 5000")
    return c


def init_db():
    con = get_conn()
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(_SCHEMA)
        con.commit()
    finally:
        con.close()


def dict_row(row):
    if row is None:
        return None
    return dict(row)


def dict_rows(rows):
    return [dict(r) for r in rows]
