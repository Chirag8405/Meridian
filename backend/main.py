"""
Meridian dashboard read API — deployed on Render, reads from Supabase
(populated by ingestion/push_to_supabase.py), serves the same combined
data shape the dashboard's static JSON exports used to provide.

Design (confirmed with the user before implementing, see ARCHITECTURE.md's
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

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_PUBLISHABLE_KEY = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")

app = FastAPI(title="Meridian Dashboard API")

TABLES = [
    "current_risk",
    "current_risk_live",
    "usdc_crisis_timeline",
    "ust_crisis_timeline",
    "classifier_metrics",
    "wallet_rankings",
]


def _require_config():
    if not SUPABASE_URL or not SUPABASE_PUBLISHABLE_KEY:
        raise HTTPException(
            status_code=500,
            detail="SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY not configured on this Render service",
        )


def _headers() -> dict:
    return {"apikey": SUPABASE_PUBLISHABLE_KEY, "Authorization": f"Bearer {SUPABASE_PUBLISHABLE_KEY}"}


async def _fetch_table(client: httpx.AsyncClient, table: str, order: str | None = None) -> list:
    params = {"select": "*"}
    if order:
        params["order"] = order
    resp = await client.get(f"{SUPABASE_URL}/rest/v1/{table}", headers=_headers(), params=params)
    resp.raise_for_status()
    return resp.json()


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
            classifier_metrics,
            wallet_rankings,
            metadata,
        ) = await asyncio.gather(
            _fetch_table(client, "current_risk", order="pair,project"),
            _fetch_table(client, "current_risk_live", order="pair,project"),
            _fetch_table(client, "usdc_crisis_timeline", order="window_start_ts"),
            _fetch_table(client, "ust_crisis_timeline", order="window_start_ts"),
            _fetch_table(client, "classifier_metrics", order="direction,scorer"),
            _fetch_table(client, "wallet_rankings", order="window_label,rank_within_window"),
            _fetch_metadata(client),
        )

    return JSONResponse({
        "current_risk": current_risk,
        "current_risk_live": current_risk_live,
        "usdc_crisis_timeline": usdc_crisis_timeline,
        "ust_crisis_timeline": ust_crisis_timeline,
        "classifier_metrics": classifier_metrics,
        "wallet_rankings": wallet_rankings,
        "metadata": metadata,
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
