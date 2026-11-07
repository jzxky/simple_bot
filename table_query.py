"""Ported from the player-hub repo (table_query.py).

Shared server-side filtering, tiered sorting and facets for table endpoints.

Query string contract (used by static/datatable.js in server mode):

- ``f.<col>=<value>`` — repeat to match any of several values for one column
  (OR within a column, AND across columns). An empty value matches blanks
  (NULL or '').
- ``sort=<col>:<asc|desc>,<col>:<asc|desc>`` — tiered sort, first tier first.
  Blank values always sort last, whatever the direction.
- ``search=<text>`` — substring match over the endpoint's search columns.
- ``facet=<col>`` (+ optional ``facet_q``) — instead of rows, return the
  distinct values of one column with counts, under every active filter except
  that column's own.

Column names are only ever taken from the caller's whitelist, so they are safe
to interpolate; every value goes through a parameter.
"""

FACET_LIMIT = 500


def parse_filters(args, columns):
    """{col: [values]} for every whitelisted column with an ``f.<col>`` param."""
    out = {}
    for col in columns:
        key = "f." + col
        if key in args:
            out[col] = args.getlist(key)
    return out


def parse_sort(raw, columns):
    """[(col, 'ASC'|'DESC')] from ``col:dir,col:dir``; unknown columns dropped."""
    tiers = []
    seen = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if not part:
            continue
        col, _, direction = part.partition(":")
        col = col.strip()
        if col not in columns or col in seen:
            continue
        seen.add(col)
        tiers.append((col, "DESC" if direction.strip().lower() == "desc" else "ASC"))
    return tiers


def where_clause(filters, search="", search_cols=(), skip=None):
    """(sql, params) for the filters, leaving out the column named ``skip``."""
    parts, params = [], []
    for col, values in filters.items():
        if col == skip or not values:
            continue
        ors = []
        concrete = [v for v in values if v != ""]
        if concrete:
            ors.append(f"[{col}] IN ({','.join('?' * len(concrete))})")
            params.extend(concrete)
        if len(concrete) != len(values):
            ors.append(f"([{col}] IS NULL OR [{col}] = '')")
        parts.append("(" + " OR ".join(ors) + ")")
    if search and search_cols:
        parts.append("(" + " OR ".join(f"[{c}] LIKE ?" for c in search_cols) + ")")
        params.extend(f"%{search}%" for _ in search_cols)
    return (" AND ".join(parts) if parts else "1=1"), params


def order_clause(tiers, tiebreak=None, numeric_cols=()):
    """ORDER BY body with blanks last on every tier, plus a stable tiebreak.

    ``numeric_cols`` are TEXT columns holding numbers (e.g. "1,250"), sorted by value.
    """
    items = []
    for col, direction in tiers:
        items.append(f"([{col}] IS NULL OR [{col}] = '')")
        if col in numeric_cols:
            items.append(f"CAST(REPLACE([{col}], ',', '') AS REAL) {direction}")
        items.append(f"[{col}] COLLATE NOCASE {direction}")
    if tiebreak and tiebreak not in [c for c, _ in tiers]:
        items.append(f"[{tiebreak}] COLLATE NOCASE ASC")
    return ", ".join(items)


def facet(con, table, col, filters, search="", search_cols=(), q="", base_where="1=1", base_params=()):
    """Distinct values of ``col`` with counts, under all filters except its own."""
    sql, params = where_clause(filters, search, search_cols, skip=col)
    params = list(base_params) + params
    if q:
        sql += f" AND [{col}] LIKE ?"
        params.append(f"%{q}%")
    rows = con.execute(
        f"SELECT COALESCE([{col}], '') AS v, COUNT(*) FROM [{table}] "
        f"WHERE ({base_where}) AND {sql} GROUP BY v ORDER BY COUNT(*) DESC, v COLLATE NOCASE "
        f"LIMIT {FACET_LIMIT + 1}",
        params,
    ).fetchall()
    # '' and NULL both collapse to one blank bucket.
    merged = {}
    for v, n in rows:
        key = "" if v is None else str(v)
        merged[key] = merged.get(key, 0) + n
    values = [{"value": k, "count": n} for k, n in merged.items()]
    return {"facet": values[:FACET_LIMIT], "truncated": len(values) > FACET_LIMIT}


def paged_query(con, table, args, columns, *, filterable=None, search_cols=(), default_sort=(),
                tiebreak=None, numeric_cols=(), per_page_default=100, per_page_max=500,
                base_where="1=1", base_params=(), legacy_filters=None):
    """Run a filtered, tier-sorted, paged SELECT * (or a facet request).

    ``legacy_filters`` maps old single-value params (e.g. ``city``) to columns so
    existing callers keep working.
    """
    filterable = list(filterable if filterable is not None else columns)
    filters = parse_filters(args, filterable)
    for param, col in (legacy_filters or {}).items():
        val = args.get(param)
        if val not in (None, "") and col not in filters:
            filters[col] = [val]
    search = args.get("search", "").strip()

    facet_col = args.get("facet")
    if facet_col is not None:
        if facet_col not in filterable:
            return None, {"error": "Unknown facet column"}
        return facet(con, table, facet_col, filters, search, search_cols,
                     args.get("facet_q", "").strip(), base_where, base_params), None

    raw_sort = args.get("sort", "")
    if raw_sort and ":" not in raw_sort and "," not in raw_sort:
        # Legacy ?sort=col&order=dir
        raw_sort = raw_sort + ":" + args.get("order", "asc")
    tiers = parse_sort(raw_sort, columns) or [t for t in default_sort if t[0] in columns]

    page = max(1, args.get("page", 1, type=int) or 1)
    per_page = args.get("per_page", per_page_default, type=int) or per_page_default
    per_page = max(1, min(per_page, per_page_max))

    sql, params = where_clause(filters, search, search_cols)
    where = f"({base_where}) AND {sql}"
    params = list(base_params) + params
    total = con.execute(f"SELECT COUNT(*) FROM [{table}] WHERE {where}", params).fetchone()[0]
    order = order_clause(tiers, tiebreak, numeric_cols)
    cur = con.execute(
        f"SELECT * FROM [{table}] WHERE {where} {'ORDER BY ' + order if order else ''} LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    )
    names = [d[0] for d in cur.description]
    rows = [dict(zip(names, r)) for r in cur.fetchall()]
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "sort": [{"key": c, "dir": d.lower()} for c, d in tiers],
    }, None

