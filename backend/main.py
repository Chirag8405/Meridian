"""
Meridian dashboard read API — deployed on Render, reads from Supabase
(populated by ingestion/push_to_supabase.py), serves the same combined
data shape the dashboard's static JSON exports used to provide.

Design (confirmed with the user before implementing, see docs/ARCHITECTURE.md's
Application Layer section for the full report):
  - Read-only: uses Supabase's publishable key (respects Row Level
    Security — see supabase/schema.sql's SELECT-only policies), never the
    secret key. This backend cannot write to Supabase even if compromised.
  - No CORS configured, deliberately — the Next.js dashboard calls this
    from a Server Component (server-to-server, Vercel -> Render), never
    directly from the browser, so CORS doesn't apply. If a client-side
    caller is ever added later, CORS middleware would need to be added
    then, not defensively now for a path not taken.
  - /health does a REAL Supabase query (not a stub) — the whole point of
    the UptimeRobot monitor hitting this endpoint every 5 minutes is to
    generate genuine Supabase traffic that keeps its free-tier project
    from pausing after 7 days of inactivity, per the confirmed design.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")

app = FastAPI(title="Meridian Dashboard API")

TABLES = [
    "current_risk",
    "current_risk_live",
    "usdc_crisis_timeline",
    "ust_crisis_timeline",
    "live_price_timeline",
    "evaluation_summary",
    "classifier_metrics",
    "wallet_rankings",
]
RECENT_EVENTS_DISPLAY_LIMIT = 25
RECENT_EVENTS_MAX_LIMIT = 100  # matches the recent_swap_events retention policy
RETENTION_HOURS = 48
# window -> (window length, bucket length). Every window yields 12-15 bars.
ACTIVITY_WINDOWS = {
    "15m": (timedelta(minutes=15), timedelta(minutes=1)),
    "1h": (timedelta(hours=1), timedelta(minutes=5)),
    "6h": (timedelta(hours=6), timedelta(minutes=30)),
    "24h": (timedelta(hours=24), timedelta(hours=2)),
}
VALID_SOURCES = {"alchemy_live", "alchemy_getlogs_replay"}


def _require_config():
    if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY not configured on this Render service",
        )


def _headers() -> dict:
    return {"apikey": SUPABASE_PUBLISHABLE_KEY, "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}"}


PAGE_SIZE = 1000  # Supabase's PostgREST caps a single response at 1000 rows


async def _fetch_table(client: httpx.AsyncClient, table: str, order: str | None = None) -> list:
    # Page with Range headers: without this, any table over 1000 rows (e.g.
    # live_price_timeline) was silently truncated to its first 1000.
    params = {"select": "*"}
    if order:
        params["order"] = order
    rows: list = []
    while True:
        headers = {**_headers(), "Range-Unit": "items", "Range": f"{len(rows)}-{len(rows) + PAGE_SIZE - 1}"}
        resp = await client.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=headers, params=params)
        resp.raise_for_status()
        page = resp.json()
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows


async def _fetch_metadata(client: httpx.AsyncClient) -> dict:
    resp = await client.get(
        f"{SUPABASE_URL}/rest/v1/metadata", headers=_headers(), params={"select": "*", "id": "eq.1"}
    )
    resp.raise_for_status()
    rows = resp.json()
    return rows[0] if rows else {}


@app.get("/api/dashboard-data")
async def dashboard_data():
    """One combined response, matching how the dashboard already consumes
    all 7 data shapes synchronously in one Server Component render —
    total payload is tiny (~68KB, confirmed before this was designed), so
    one request is simpler than seven for no real cost."""
    _require_config()
    async with httpx.AsyncClient(timeout=15.0) as client:
        (
            current_risk,
            current_risk_live,
            usdc_crisis_timeline,
            ust_crisis_timeline,
            live_price_timeline,
            evaluation_summary,
            classifier_metrics,
            wallet_rankings,
            metadata,
        ) = await asyncio.gather(
            _fetch_table(client, "current_risk", order="pair,project"),
            _fetch_table(client, "current_risk_live", order="pair,project"),
            _fetch_table(client, "usdc_crisis_timeline", order="window_start_ts"),
            _fetch_table(client, "ust_crisis_timeline", order="window_start_ts"),
            _fetch_table(client, "live_price_timeline", order="pair,project,window_start_ts"),
            _fetch_table(client, "evaluation_summary", order="event_label"),
            _fetch_table(client, "classifier_metrics", order="direction,scorer"),
            _fetch_table(client, "wallet_rankings", order="window_label,rank_within_window"),
            _fetch_metadata(client),
        )

    return JSONResponse({
        "current_risk": current_risk,
        "current_risk_live": current_risk_live,
        "usdc_crisis_timeline": usdc_crisis_timeline,
        "ust_crisis_timeline": ust_crisis_timeline,
        "live_price_timeline": live_price_timeline,
        "evaluation_summary": evaluation_summary,
        "classifier_metrics": classifier_metrics,
        "wallet_rankings": wallet_rankings,
        "metadata": metadata,
    })


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_source(source: str | None):
    if source is not None and source not in VALID_SOURCES:
        raise HTTPException(status_code=422, detail=f"source must be one of {sorted(VALID_SOURCES)}")


async def _fetch_recent_rows() -> list:
    async with httpx.AsyncClient(timeout=5.0) as client:
        return await _fetch_table(
            client,
            "recent_swap_events",
            order="observed_at.desc,event_id.desc",
        )


def _matches(row: dict, pair: str | None, pool: str | None, source: str | None) -> bool:
    if pair is not None and (row.get("pair") or "untracked") != pair:
        return False
    if pool is not None and row["pool_name"] != pool:
        return False
    return source is None or row["source"] == source


@app.get("/api/recent-swap-events")
async def recent_swap_events(
    pair: str | None = Query(None, max_length=64),
    pool: str | None = Query(None, max_length=64),
    source: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(RECENT_EVENTS_DISPLAY_LIMIT, ge=1, le=RECENT_EVENTS_MAX_LIMIT),
):
    """Raw events, newest first. With no parameters this is the original
    25-row display feed; filters/start/end (by observed_at, [start, end))
    let the dashboard inspect one activity bucket."""
    _require_config()
    _validate_source(source)
    rows = await _fetch_recent_rows()
    lo = start.astimezone(timezone.utc) if start else None
    hi = end.astimezone(timezone.utc) if end else None
    out = []
    for r in rows:
        if not _matches(r, pair, pool, source):
            continue
        observed = _parse_ts(r["observed_at"])
        if (lo and observed < lo) or (hi and observed >= hi):
            continue
        out.append(r)
    return JSONResponse(out[:limit])


@app.get("/api/recent-swap-activity")
async def recent_swap_activity(
    window: str = "1h",
    pair: str | None = Query(None, max_length=64),
    pool: str | None = Query(None, max_length=64),
    source: str | None = None,
):
    """Aggregated feed activity: swap counts per UTC-aligned bucket of
    observed_at (when the feed saw the event, not the on-chain event_ts).
    Zero-count buckets are returned so quiet periods stay visible. Counts
    are descriptive only, never a risk signal."""
    _require_config()
    if window not in ACTIVITY_WINDOWS:
        raise HTTPException(status_code=422, detail=f"window must be one of {list(ACTIVITY_WINDOWS)}")
    _validate_source(source)
    rows = await _fetch_recent_rows()

    window_len, bucket_len = ACTIVITY_WINDOWS[window]
    now = datetime.now(timezone.utc)
    bucket_s = int(bucket_len.total_seconds())
    end_epoch = (int(now.timestamp()) // bucket_s + 1) * bucket_s  # end of the current bucket
    window_end = datetime.fromtimestamp(end_epoch, timezone.utc)
    window_start = window_end - window_len

    filter_options = {
        "pairs": sorted({r.get("pair") or "untracked" for r in rows}),
        "pools": sorted({r["pool_name"] for r in rows}),
        "sources": sorted({r["source"] for r in rows}),
    }

    buckets = []
    cursor = window_start
    while cursor < window_end:
        buckets.append({
            "start": cursor, "end": cursor + bucket_len, "total": 0, "live": 0, "gap_filled": 0,
        })
        cursor += bucket_len

    filtered = [r for r in rows if _matches(r, pair, pool, source)]
    in_window = []
    for r in filtered:
        observed = _parse_ts(r["observed_at"])
        if not (window_start <= observed < window_end):
            continue
        in_window.append(r)
        b = buckets[int((observed - window_start) / bucket_len)]
        b["total"] += 1
        b["live" if r["source"] == "alchemy_live" else "gap_filled"] += 1

    oldest = min((_parse_ts(r["observed_at"]) for r in rows), default=None)
    newest = max((_parse_ts(r["observed_at"]) for r in filtered), default=None)
    live = sum(1 for r in in_window if r["source"] == "alchemy_live")
    return JSONResponse({
        "window": window,
        "bucket_seconds": bucket_s,
        "window_start": _iso(window_start),
        "window_end": _iso(window_end),
        "buckets": [
            {**b, "start": _iso(b["start"]), "end": _iso(b["end"])} for b in buckets
        ],
        "summary": {
            "total": len(in_window),
            "live": live,
            "gap_filled": len(in_window) - live,
            "active_pools": len({r["pool_name"] for r in in_window}),
            "last_observed_at": _iso(newest) if newest else None,
        },
        "filter_options": filter_options,
        "retention": {
            "retained_rows": len(rows),
            "retention_hours": RETENTION_HOURS,
            "max_rows": RECENT_EVENTS_MAX_LIMIT,
            "oldest_observed_at": _iso(oldest) if oldest else None,
            # True when the selected window reaches back past what is retained.
            "window_exceeds_retention": oldest is not None and oldest > window_start,
        },
    })


@app.get("/health")
async def health():
    """Genuinely queries Supabase (SELECT on the smallest table) rather
    than just returning 200 unconditionally — this endpoint's real job is
    generating actual Supabase traffic for UptimeRobot's pings, not just
    confirming this process is alive."""
    _require_config()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{SUPABASE_URL}/rest/v1/metadata", headers=_headers(),
                params={"select": "id", "limit": "1"},
            )
            resp.raise_for_status()
        return {"status": "ok", "supabase": "reachable"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Supabase unreachable: {e!r}")
