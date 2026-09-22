# Player Hub API Documentation

Base URL: `http://<host>:9090`

## Authentication

### Bot clients
All `/api/sync/*` endpoints require an API key in the `Authorization` header:
```
Authorization: Bearer <api_key>
```
API keys are generated when an admin registers a client via the web UI.

### Web users
All `/api/crud/*` and `/api/admin/*` endpoints require a logged-in session (cookie-based).

---

## Sync API (Bot-Facing)

### GET /api/sync/health
No auth required. Returns server status.
```json
{"ok": true, "player_count": 150}
```

### POST /api/sync/push
Push player data, groups, and career history from a bot client.

**Body:**
```json
{
  "players": [
    {
      "username": "PlayerName",
      "homecity": "New York",
      "occupation": "Bodyguard",
      "rank": "Earner",
      "active": 1,
      "character_age": 500,
      "jail_age": 0,
      "group_name": "MyGroup",
      "agg_crimes": "10",
      "case_work": "5",
      "scraped_at": "2024-01-01T00:00:00Z",
      "assignments_updated_at": "2024-01-01T00:00:00Z",
      "pic_url": "",
      "sex": "Male",
      "wealth": "Rich",
      "scripting": "",
      "godfather": "",
      "crew_name": "",
      "capos": "",
      "alias": "",
      "notes": "",
      "monitoring": 0,
      "born_at": "",
      "died_at": "",
      "respect": "",
      "respect_last_checked": 0
    }
  ],
  "groups": [
    {"name": "MyGroup", "color": "#3498db", "type": "neutral", "agg_crimes": "", "case_work": "", "updated_at": ""}
  ],
  "career": [
    {"username": "PlayerName", "ts": "2024-01-01T00:00:00Z", "rank": "Earner", "occupation": "Bodyguard", "homecity": "New York"}
  ]
}
```

**Conflict resolution:**
- `character_age`, `jail_age`: MAX wins
- `homecity`, `occupation`, `rank`: last-write-wins on `scraped_at`
- `agg_crimes`, `case_work`, `group_name`: last-write-wins on `assignments_updated_at`
- `career_history`: INSERT OR IGNORE by unique key (username, ts, rank, occupation, homecity)
- `groups`: last-write-wins on `updated_at`

**Response:**
```json
{"ok": true, "server_time": "2024-01-01T00:00:00Z"}
```

### GET /api/sync/pull?since=<timestamp>
Pull changes since a timestamp.

**Response:**
```json
{
  "players": [...],
  "groups": [...],
  "career": [...],
  "server_time": "2024-01-01T00:00:00Z"
}
```

### GET /api/sync/groups/full
Get all groups.

**Response:**
```json
{"groups": [...]}
```

---

## War Sync API (Bot-Facing)

### GET /api/sync/war/lists
Get current war entries (who to monitor).

**Response:**
```json
{
  "opps": [{"name": "...", "ws": 0, "whack_type": "Normal", ...}],
  "friendlies": [...]
}
```

### POST /api/sync/war/record_ws
Record a WS change (only increases).

**Body:**
```json
{"name": "PlayerName", "ws": 5}
```

### POST /api/sync/war/check_update
Update last_checked timestamp for a war entry.

**Body:**
```json
{"name": "PlayerName"}
```

---

## CRUD API (Web UI)

### GET /api/crud/players
List players with pagination, search, filtering, and sorting.

**Query params:** `page`, `per_page`, `search`, `sort`, `order`, `active`, `group`, `city`, `occupation`, `rank`

### GET /api/crud/players/<username>
Get player detail including career history.

### PUT /api/crud/players/<username>
Update editable fields: `group_name`, `agg_crimes`, `case_work`, `alias`, `notes`, `monitoring`.

### DELETE /api/crud/players/<username>
Delete player and career history. **Admin only.**

### GET /api/crud/groups
List all groups with member counts.

### POST /api/crud/groups
Create group. Body: `{name, color, type}`

### PUT /api/crud/groups/<name>
Update group. Body: `{color, type, agg_crimes, case_work}`

### POST /api/crud/groups/<name>/rename
Rename group. Body: `{new_name}`

### DELETE /api/crud/groups/<name>
Delete group. **Admin only.**

### GET /api/crud/groups/<name>/members
List group members.

### GET /api/crud/clients
List registered bot clients.

### PUT /api/crud/clients/<client_id>
Update client label.

### GET /api/crud/war/state
Get full war state (opps, friendlies, events with computed status).

### POST /api/crud/war/add
Add war entry. Body: `{name, side}`

### POST /api/crud/war/remove
Remove war entry. Body: `{name, side}`

### POST /api/crud/war/update
Update war entry. Body: `{name, side, ws?, whack_type?, last_whack_time?}`

### POST /api/crud/war/clear_events
Clear all war events.

### GET /api/crud/filter_options
Get distinct values for filter dropdowns.

### GET /api/crud/sync_log
View sync activity log. Query: `page`, `per_page`.

---

## Admin API

### GET /api/admin/tables
List all database tables with row counts.

### GET /api/admin/tables/<name>
View table rows. Query: `page`, `per_page`.

### DELETE /api/admin/tables/<name>/<pk_value>
Delete a row by primary key.

### GET /api/admin/users
List all users.

### POST /api/admin/users
Create user. Body: `{username, password, role}`

### PUT /api/admin/users/<id>
Update user. Body: `{role?, password?}`

### DELETE /api/admin/users/<id>
Delete user.

### POST /api/admin/clients
Register new bot client. Body: `{client_id, label}`. Returns API key (shown once).

### DELETE /api/admin/clients/<client_id>
Revoke client (sets active=0).

---

## Bot Client Integration

To connect a `simple_bot` instance to Player Hub:

1. Admin registers a client via the web UI → gets an API key
2. In the bot's config, set:
   - `sync.url`: `http://<hub_host>:9090`
   - `sync.client_id`: the registered client ID
   - `sync.api_key`: the API key from registration
3. Update `sync_client.py` to:
   - Send `Authorization: Bearer <api_key>` header on all requests
   - Use `/api/sync/push` and `/api/sync/pull` endpoints
   - Include all player fields in push payload
4. Update `war_mode.py` to:
   - Fetch watch lists from `/api/sync/war/lists`
   - Report WS changes to `/api/sync/war/record_ws`
   - Report check times to `/api/sync/war/check_update`
