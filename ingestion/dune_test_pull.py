"""
Schema/data-quality test pull from Dune Analytics — NOT the production
ingestion pipeline. Confirms Dune's data actually shows the March 2023 USDC
depeg before we design the Hive schema around it.

Pulls hourly-aggregated implied USDC/USDT price from Curve's 3pool
(DAI/USDC/USDT, 0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7) for a 1-week
window around the SVB weekend (2023-03-09 to 2023-03-14 UTC), computed from
raw swap trades in Dune's `dex.trades` table. Aggregating to hourly buckets
keeps the row count (~120) and credit cost low on the free tier, instead of
pulling every individual trade (3pool saw ~$6B volume on 2023-03-11 alone).

Writes the raw API response to data/raw/dune_test_pull.json for inspection.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
OUTPUT_FILE = PROJECT_ROOT / "data" / "raw" / "dune_test_pull.json"

DUNE_API_BASE = "https://api.dune.com/api/v1"
CURVE_3POOL_ADDRESS = "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7"

SQL_QUERY = f"""
SELECT
  date_trunc('hour', block_time) AS hour,
  count(*) AS trade_count,
  sum(amount_usd) AS volume_usd,
  avg(
    CASE
      WHEN token_sold_symbol = 'USDC' AND token_bought_symbol = 'USDT'
        THEN token_bought_amount / token_sold_amount
      WHEN token_sold_symbol = 'USDT' AND token_bought_symbol = 'USDC'
        THEN token_sold_amount / token_bought_amount
    END
  ) AS usdc_per_usdt_implied_price
FROM dex.trades
WHERE blockchain = 'ethereum'
  AND project = 'curve'
  AND project_contract_address = {CURVE_3POOL_ADDRESS}
  AND block_time >= TIMESTAMP '2023-03-09 00:00:00'
  AND block_time < TIMESTAMP '2023-03-14 00:00:00'
  AND (
    (token_sold_symbol = 'USDC' AND token_bought_symbol = 'USDT')
    OR (token_sold_symbol = 'USDT' AND token_bought_symbol = 'USDC')
  )
GROUP BY 1
ORDER BY 1
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


def execute_sql(api_key: str) -> str:
    resp = requests.post(
        f"{DUNE_API_BASE}/sql/execute",
        headers={"X-Dune-Api-Key": api_key, "Content-Type": "application/json"},
        json={"sql": SQL_QUERY, "performance": "medium"},
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    print(f"Submitted execution: {body['execution_id']} (state={body['state']})")
    return body["execution_id"]


def poll_until_done(api_key: str, execution_id: str, timeout_s: int = 300) -> dict:
    deadline = time.time() + timeout_s
    url = f"{DUNE_API_BASE}/execution/{execution_id}/results"
    while time.time() < deadline:
        resp = requests.get(url, headers={"X-Dune-Api-Key": api_key}, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        state = body.get("state")
        print(f"  state={state}")
        if body.get("is_execution_finished"):
            return body
        time.sleep(3)
    sys.exit(f"Timed out after {timeout_s}s waiting for execution {execution_id}")


def main() -> None:
    api_key = load_api_key()

    print("Executing SQL against Dune...")
    try:
        execution_id = execute_sql(api_key)
    except requests.HTTPError as e:
        print(f"ERROR executing SQL: {e}")
        print(e.response.text)
        sys.exit(1)

    print("Polling for results...")
    result = poll_until_done(api_key, execution_id)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(result, indent=2))
    print(f"\nWrote raw response to {OUTPUT_FILE}")

    if result.get("state") != "QUERY_STATE_COMPLETED":
        print(f"\nQuery did not complete successfully: {result.get('state')}")
        print(json.dumps(result.get("error", result), indent=2))
        sys.exit(1)

    metadata = result["result"]["metadata"]
    rows = result["result"]["rows"]

    print("\n=== SCHEMA ===")
    for name, dtype in zip(metadata["column_names"], metadata["column_types"]):
        print(f"  {name}: {dtype}")
    print(f"\nrow_count={metadata['row_count']}  "
          f"total_row_count={metadata.get('total_row_count')}  "
          f"execution_time_ms={metadata.get('execution_time_millis')}  "
          f"datapoint_count={metadata.get('datapoint_count')}")

    print("\n=== SAMPLE ROWS (first 10) ===")
    for row in rows[:10]:
        print(row)

    print("\n=== DEPEG CHECK ===")
    def as_finite_float(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f and abs(f) != float("inf") else None  # filter NaN/Inf

    priced_rows = [
        r for r in rows
        if as_finite_float(r.get("usdc_per_usdt_implied_price")) is not None
    ]
    skipped = len(rows) - len(priced_rows)
    if skipped:
        print(f"(skipped {skipped} row(s) with null/NaN implied price — "
              f"likely a degenerate trade, e.g. zero-amount leg)")

    if not priced_rows:
        print("No hours with USDC<->USDT trades found in this window.")
    else:
        prices = [as_finite_float(r["usdc_per_usdt_implied_price"]) for r in priced_rows]
        min_price, max_price = min(prices), max(prices)
        min_row = next(r for r in priced_rows
                       if as_finite_float(r["usdc_per_usdt_implied_price"]) == min_price)
        print(f"Implied USDC/USDT price range: {min_price:.4f} - {max_price:.4f}")
        print(f"Lowest point: {min_row['hour']}  price={min_price:.4f}  "
              f"trades={min_row['trade_count']}  volume_usd={min_row['volume_usd']:.0f}")
        deviation_pct = (1.0 - min_price) * 100
        if deviation_pct > 1.0:
            print(f"DEPEG VISIBLE: price dropped {deviation_pct:.2f}% below 1:1 "
                  f"within the window.")
        else:
            print(f"No clear depeg signal (max deviation from 1:1 was "
                  f"{deviation_pct:.2f}%).")


if __name__ == "__main__":
    main()
