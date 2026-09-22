# Claude Code Instructions for player_hub

## Project Overview

Player Hub is a centralized web app for managing player databases across multiple bot instances. It replaces `sync_server.py` and provides authenticated REST API for bot clients plus a web UI for human users.

## Stack

- Python 3 / Flask (synchronous, no async)
- SQLite with WAL mode for concurrent access
- Vanilla JavaScript (no frameworks)
- bcrypt for password hashing, SHA-256 for API key hashing

## Project Rules

- No async — synchronous Python with threading only
- `.env`, `player_hub.db` must always be in `.gitignore` and never committed
- Dark theme CSS uses custom properties from `:root` block in `style.css`
- All bot-facing endpoints use API key auth (`Authorization: Bearer <key>`)
- All UI-facing endpoints use Flask session auth
- Admin-only routes use `@admin_required` decorator
- War mode window computation uses constants from `war_mode.py` in simple_bot

## File Layout

- `app.py` — Flask entry point, page routes
- `db.py` — Database layer, schema, WAL setup
- `auth.py` — User accounts, API key auth, decorators
- `sync_api.py` — Bot-facing sync endpoints (Blueprint at `/api/sync`)
- `crud_api.py` — UI-facing CRUD endpoints (Blueprint at `/api/crud`)
- `war_api.py` — War mode endpoints (mixed UI + bot-facing)
- `admin_api.py` — Admin endpoints (Blueprint at `/api/admin`)
- `static/` — CSS + JS assets
- `templates/` — Jinja2 templates

## Running

```bash
cp .env.example .env  # edit with real values
pip install -r requirements.txt
python app.py
```

First admin user is seeded from `ADMIN_USER` / `ADMIN_PASS` env vars.
