"""
Pushes the dashboard's local JSON exports (dashboard/data/*.json, written
by spark/export_dashboard_data.scala) to Supabase, so the live Render
backend has something fresh to serve. Run this manually right after the
Spark export, same "batch job, rerun by hand" operating model as
everything else in this project — see SETUP.md's "Live backend
(Supabase + Render)" section for the full workflow.

Uses Supabase's REST API (PostgREST) via plain HTTP, not a Postgres
driver — the data volume here is tiny (68KB total, confirmed empirically
before this was designed) and this project already has a proven
"read local data, POST via requests" pattern (see
ingestion/alchemy_live_feed.py's CoinGecko integration), so a new DB
driver dependency isn't worth adding for this.

Uses the sb_secret_... key (bypasses Row Level Security — see
supabase/schema.sql) — this is a WRITE credential and must only ever live
in this machine's .env, never on Render (which only needs read access via
the publishable key) and never anywhere near the Vercel/frontend side.

Each table is fully replaced (delete all + insert) on every run, matching
the existing export's "overwrite the whole file" semantics exactly — the
data volume and push frequency here don't warrant incremental/upsert
logic.
"""

import json
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
DATA_DIR = PROJECT_ROOT / "dashboard" / "data"

# JSON filename -> Supabase table name. metadata.json is a single object,
# not an array — handled separately below (single-row table).
TABLE_FILES = {
    "current_risk.json": "current_risk",
    "current_risk_live.json": "current_risk_live",
    "usdc_crisis_timeline.json": "usdc_crisis_timeline",
    "ust_crisis_timeline.json": "ust_crisis_timeline",
    "classifier_metrics.json": "classifier_metrics",
    "wallet_rankings.json": "wallet_rankings",
}


def load_env() -> dict:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE} — see .env.example")
    env = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def require(env: dict, key: str) -> str:
    val = env.get(key, "")
    if not val:
        sys.exit(f"{key} not set in .env — see .env.example")
    return val


def replace_table(base_url: str, headers: dict, table: str, rows: list):
    """Delete all existing rows, then insert the new set — a full
    replace, not an incremental upsert (see module docstring for why)."""
    # PostgREST requires a filter on DELETE against a whole table; every
    # table here has a real primary key column we can safely filter
    # "not null" against to mean "everything".
    pk_col = {
        "current_risk": "pair", "current_risk_live": "pair",
        "usdc_crisis_timeline": "window_start_ts", "ust_crisis_timeline": "window_start_ts",
        "classifier_metrics": "direction", "wallet_rankings": "window_label",
    }[table]
    del_resp = requests.delete(
        f"{base_url}/rest/v1/{table}", headers=headers,
        params={pk_col: "not.is.null"}, timeout=30,
    )
    del_resp.raise_for_status()

    if not rows:
        print(f"  {table}: cleared, 0 rows to insert (empty export)")
        return

    ins_resp = requests.post(
        f"{base_url}/rest/v1/{table}", headers=headers, json=rows, timeout=30,
    )
    ins_resp.raise_for_status()
    print(f"  {table}: replaced with {len(rows)} row(s)")


def replace_metadata(base_url: str, headers: dict, meta: dict):
    row = {**meta, "id": 1}
    resp = requests.post(
        f"{base_url}/rest/v1/metadata", headers={**headers, "Prefer": "resolution=merge-duplicates"},
        json=row, timeout=30,
    )
    resp.raise_for_status()
    print("  metadata: upserted")


def main():
    env = load_env()
    supabase_url = require(env, "SUPABASE_URL").rstrip("/")
    secret_key = require(env, "SUPABASE_SECRET_KEY")

    headers = {
        "apikey": secret_key,
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    if not DATA_DIR.exists():
        sys.exit(f"{DATA_DIR} does not exist — run spark/export_dashboard_data.scala first")

    print(f"Pushing dashboard data to {supabase_url} ...")
    for filename, table in TABLE_FILES.items():
        path = DATA_DIR / filename
        if not path.exists():
            print(f"  {table}: SKIPPED — {path} not found")
            continue
        rows = json.loads(path.read_text())
        replace_table(supabase_url, headers, table, rows)

    meta_path = DATA_DIR / "metadata.json"
    if meta_path.exists():
        replace_metadata(supabase_url, headers, json.loads(meta_path.read_text()))
    else:
        print("  metadata: SKIPPED — metadata.json not found")

    print("\nDone.")


if __name__ == "__main__":
    main()
