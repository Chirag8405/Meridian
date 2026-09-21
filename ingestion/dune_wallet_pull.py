"""
Wallet-level trade data pull for the PageRank wallet/pool influence analysis
— a new, separate pull from the hourly-aggregated dune_backfill.py /
dune_ust_backfill.py. Selects taker/tx_from/tx_to + trade fields per
individual trade (no aggregation), across the same 4 pools and windows
already scoped for the historical backfill.

`taker` is used as the wallet identity for the bipartite graph — it's
Dune's own resolved "who executed this swap" field. tx_from/tx_to are also
captured for the router/aggregator data-quality check (a taker whose
address is a known contract, not an EOA, is infrastructure everyone routes
through, not an influential trader — see spark/wallet_pagerank.scala).

Handles pagination since the full pull (~135K rows) exceeds a single
results page. Writes raw paginated JSON to data/raw/, then a combined
staging TSV for Spark.
"""

import json
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "dune_wallet_pull"
STAGING_FILE = PROJECT_ROOT / "data" / "processed" / "wallet_trades.tsv"

DUNE_API_BASE = "https://api.dune.com/api/v1"

CURVE_3POOL_ADDRESS = "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7"
UNISWAP_USDC_USDT_ADDRESS = "0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f"
UNISWAP_USDC_DAI_ADDRESS = "0xAe461cA67B15dc8dc81CE7615e0320Da1A9aB8D5"
UST_METAPOOL_ADDRESS = "0x890f4e345B1dAED0367A877a1612f86A1f86985f"

SQL = f"""
SELECT
  taker,
  tx_from,
  tx_to,
  project_contract_address AS pool_address,
  amount_usd,
  block_time
FROM dex.trades
WHERE blockchain = 'ethereum'
  AND (
    (project_contract_address = {CURVE_3POOL_ADDRESS}
      AND block_time >= TIMESTAMP '2022-12-01 00:00:00' AND block_time < TIMESTAMP '2023-06-01 00:00:00')
    OR (project_contract_address = {UNISWAP_USDC_USDT_ADDRESS}
      AND block_time >= TIMESTAMP '2022-12-01 00:00:00' AND block_time < TIMESTAMP '2023-06-01 00:00:00')
    OR (project_contract_address = {UNISWAP_USDC_DAI_ADDRESS}
      AND block_time >= TIMESTAMP '2022-12-01 00:00:00' AND block_time < TIMESTAMP '2023-06-01 00:00:00')
    OR (project_contract_address = {UST_METAPOOL_ADDRESS}
      AND block_time >= TIMESTAMP '2022-04-15 00:00:00' AND block_time < TIMESTAMP '2022-06-15 00:00:00')
  )
ORDER BY block_time
""".strip()


def load_api_key() -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE} — see .env.example")
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("DUNE_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    sys.exit("DUNE_API_KEY not set in .env")


def get_usage(api_key: str) -> dict:
    resp = requests.post(f"{DUNE_API_BASE}/usage",
        headers={"X-Dune-Api-Key": api_key, "Content-Type": "application/json"},
        json={}, timeout=30)
    resp.raise_for_status()
    return resp.json()["billing_periods"][0]


def execute_sql(api_key: str, sql: str) -> str:
    resp = requests.post(f"{DUNE_API_BASE}/sql/execute",
        headers={"X-Dune-Api-Key": api_key, "Content-Type": "application/json"},
        json={"sql": sql, "performance": "medium"}, timeout=30)
    resp.raise_for_status()
    return resp.json()["execution_id"]


def poll_until_done(api_key: str, execution_id: str, timeout_s: int = 300) -> dict:
    deadline = time.time() + timeout_s
    url = f"{DUNE_API_BASE}/execution/{execution_id}/results?limit=1"
    while time.time() < deadline:
        resp = requests.get(url, headers={"X-Dune-Api-Key": api_key}, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        if body.get("is_execution_finished"):
            return body
        time.sleep(3)
    sys.exit(f"Timed out waiting for execution {execution_id}")


def fetch_all_pages(api_key: str, execution_id: str) -> list:
    all_rows = []
    page = 0
    url = f"{DUNE_API_BASE}/execution/{execution_id}/results?limit=50000"
    while url:
        resp = requests.get(url, headers={"X-Dune-Api-Key": api_key}, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        rows = body["result"]["rows"]
        all_rows.extend(rows)
        page += 1
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DIR / f"page_{page:03d}.json").write_text(json.dumps(body, indent=2))
        print(f"  page {page}: {len(rows)} rows (total so far: {len(all_rows)})")
        next_uri = body["result"].get("next_uri") or body.get("next_uri")
        url = next_uri
    return all_rows


def main():
    api_key = load_api_key()
    STAGING_FILE.parent.mkdir(parents=True, exist_ok=True)

    usage_before = get_usage(api_key)
    print(f"Credits before: {usage_before['credits_used']} / {usage_before['credits_included']}")

    print("Executing wallet-level pull...")
    execution_id = execute_sql(api_key, SQL)
    print(f"execution_id={execution_id}, polling...")
    result = poll_until_done(api_key, execution_id)

    if result.get("state") != "QUERY_STATE_COMPLETED":
        print(f"FAILED: {result.get('state')}")
        print(json.dumps(result.get("error", result), indent=2))
        sys.exit(1)

    print(f"Query completed, total_row_count={result['result']['metadata'].get('total_row_count')}")
    print("Fetching all pages...")
    rows = fetch_all_pages(api_key, execution_id)
    print(f"Total rows fetched: {len(rows)}")

    staging_rows = []
    for row in rows:
        taker = row.get("taker") or ""
        tx_from = row.get("tx_from") or ""
        tx_to = row.get("tx_to") or ""
        pool_address = row["pool_address"]
        amount_usd = row.get("amount_usd")
        block_time = row["block_time"].replace(" UTC", "")
        dt = block_time.split(" ")[0]
        staging_rows.append("\t".join([
            taker, tx_from, tx_to, pool_address,
            repr(amount_usd) if amount_usd is not None else "\\N",
            block_time, dt,
        ]))

    STAGING_FILE.write_text("\n".join(staging_rows) + "\n")
    print(f"Wrote {len(staging_rows)} staging rows to {STAGING_FILE}")

    usage_after = get_usage(api_key)
    credits_used = usage_after["credits_used"] - usage_before["credits_used"]
    print(f"\nCredits after: {usage_after['credits_used']} / {usage_after['credits_included']}")
    print(f"Credits consumed by this pull: {credits_used:.4f}")


if __name__ == "__main__":
    main()
