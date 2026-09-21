"""
Real historical backfill via Dune — supersedes the 5-day test slice from
dune_test_pull.py. Pulls 6 months of hourly aggregated trade data
(2022-12-01 to 2023-06-01 UTC: ~3 months before/after the March 2023 USDC
depeg) for three pools, writes raw responses to data/raw/, then a combined
staging file ready to load into HDFS + the Hive table in hive/schema.sql.

Pools (all USDC/USDT/DAI — NOT UST; see project docs for that scope gap):
  - Curve 3pool (DAI/USDC/USDT): both USDC_USDT and USDC_DAI pairs in one
    combined query (per the ~15-credit estimate from the earlier test pull)
  - Uniswap V2 USDC/USDT: 0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f
  - Uniswap V2 USDC/DAI:  0xAe461cA67B15dc8dc81CE7615e0320Da1A9aB8D5

This script does NOT load into Hive itself — see hive/load_backfill.sql and
the loading steps run separately, so the raw pull and the load can be
inspected independently.
"""

import json
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
STAGING_FILE = PROJECT_ROOT / "data" / "processed" / "stablecoin_pool_hourly_backfill.tsv"

DUNE_API_BASE = "https://api.dune.com/api/v1"

CURVE_3POOL_ADDRESS = "0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7"
UNISWAP_USDC_USDT_ADDRESS = "0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f"
UNISWAP_USDC_DAI_ADDRESS = "0xAe461cA67B15dc8dc81CE7615e0320Da1A9aB8D5"

BACKFILL_START = "2022-12-01 00:00:00"
BACKFILL_END = "2023-06-01 00:00:00"

CURVE_SQL = f"""
WITH curve_trades AS (
  SELECT block_time, token_sold_symbol, token_bought_symbol,
         token_sold_amount, token_bought_amount, amount_usd
  FROM dex.trades
  WHERE blockchain = 'ethereum'
    AND project = 'curve'
    AND project_contract_address = {CURVE_3POOL_ADDRESS}
    AND block_time >= TIMESTAMP '{BACKFILL_START}'
    AND block_time < TIMESTAMP '{BACKFILL_END}'
)
SELECT
  date_trunc('hour', block_time) AS hour,
  'USDC_USDT' AS pair,
  count(*) AS trade_count,
  sum(amount_usd) AS volume_usd,
  avg(CASE
        WHEN token_sold_symbol = 'USDC' AND token_bought_symbol = 'USDT'
          THEN token_bought_amount / token_sold_amount
        WHEN token_sold_symbol = 'USDT' AND token_bought_symbol = 'USDC'
          THEN token_sold_amount / token_bought_amount
      END) AS implied_price
FROM curve_trades
WHERE (token_sold_symbol = 'USDC' AND token_bought_symbol = 'USDT')
   OR (token_sold_symbol = 'USDT' AND token_bought_symbol = 'USDC')
GROUP BY 1
UNION ALL
SELECT
  date_trunc('hour', block_time) AS hour,
  'USDC_DAI' AS pair,
  count(*) AS trade_count,
  sum(amount_usd) AS volume_usd,
  avg(CASE
        WHEN token_sold_symbol = 'USDC' AND token_bought_symbol = 'DAI'
          THEN token_bought_amount / token_sold_amount
        WHEN token_sold_symbol = 'DAI' AND token_bought_symbol = 'USDC'
          THEN token_sold_amount / token_bought_amount
      END) AS implied_price
FROM curve_trades
WHERE (token_sold_symbol = 'USDC' AND token_bought_symbol = 'DAI')
   OR (token_sold_symbol = 'DAI' AND token_bought_symbol = 'USDC')
GROUP BY 1
ORDER BY 1
""".strip()


def uniswap_pair_sql(pool_address: str, pair_label: str, other_symbol: str) -> str:
    return f"""
SELECT
  date_trunc('hour', block_time) AS hour,
  '{pair_label}' AS pair,
  count(*) AS trade_count,
  sum(amount_usd) AS volume_usd,
  avg(CASE
        WHEN token_sold_symbol = 'USDC' AND token_bought_symbol = '{other_symbol}'
          THEN token_bought_amount / token_sold_amount
        WHEN token_sold_symbol = '{other_symbol}' AND token_bought_symbol = 'USDC'
          THEN token_sold_amount / token_bought_amount
      END) AS implied_price
FROM dex.trades
WHERE blockchain = 'ethereum'
  AND project_contract_address = {pool_address}
  AND block_time >= TIMESTAMP '{BACKFILL_START}'
  AND block_time < TIMESTAMP '{BACKFILL_END}'
  AND (
    (token_sold_symbol = 'USDC' AND token_bought_symbol = '{other_symbol}')
    OR (token_sold_symbol = '{other_symbol}' AND token_bought_symbol = 'USDC')
  )
GROUP BY 1
ORDER BY 1
""".strip()


POOLS = [
    {
        "name": "curve_3pool",
        "project": "curve",
        "pool_address": CURVE_3POOL_ADDRESS,
        "sql": CURVE_SQL,
        "raw_file": RAW_DIR / "dune_backfill_curve_3pool.json",
    },
    {
        "name": "uniswap_v2_usdc_usdt",
        "project": "uniswap_v2",
        "pool_address": UNISWAP_USDC_USDT_ADDRESS,
        "sql": uniswap_pair_sql(UNISWAP_USDC_USDT_ADDRESS, "USDC_USDT", "USDT"),
        "raw_file": RAW_DIR / "dune_backfill_uniswap_usdc_usdt.json",
    },
    {
        "name": "uniswap_v2_usdc_dai",
        "project": "uniswap_v2",
        "pool_address": UNISWAP_USDC_DAI_ADDRESS,
        "sql": uniswap_pair_sql(UNISWAP_USDC_DAI_ADDRESS, "USDC_DAI", "DAI"),
        "raw_file": RAW_DIR / "dune_backfill_uniswap_usdc_dai.json",
    },
]


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
    resp = requests.post(
        f"{DUNE_API_BASE}/usage",
        headers={"X-Dune-Api-Key": api_key, "Content-Type": "application/json"},
        json={},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["billing_periods"][0]


def execute_sql(api_key: str, sql: str) -> str:
    resp = requests.post(
        f"{DUNE_API_BASE}/sql/execute",
        headers={"X-Dune-Api-Key": api_key, "Content-Type": "application/json"},
        json={"sql": sql, "performance": "medium"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["execution_id"]


def poll_until_done(api_key: str, execution_id: str, timeout_s: int = 300) -> dict:
    deadline = time.time() + timeout_s
    url = f"{DUNE_API_BASE}/execution/{execution_id}/results"
    while time.time() < deadline:
        resp = requests.get(url, headers={"X-Dune-Api-Key": api_key}, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        if body.get("is_execution_finished"):
            return body
        time.sleep(3)
    sys.exit(f"Timed out waiting for execution {execution_id}")


def as_finite_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def main():
    api_key = load_api_key()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_FILE.parent.mkdir(parents=True, exist_ok=True)

    usage_before = get_usage(api_key)
    print(f"Credits before: {usage_before['credits_used']} / {usage_before['credits_included']}")
    print(f"Backfill window: {BACKFILL_START} to {BACKFILL_END} UTC\n")

    staging_rows = []
    pool_row_counts = {}

    for pool in POOLS:
        print(f"=== {pool['name']} ===")
        execution_id = execute_sql(api_key, pool["sql"])
        print(f"  execution_id={execution_id}, polling...")
        result = poll_until_done(api_key, execution_id)

        pool["raw_file"].write_text(json.dumps(result, indent=2))
        print(f"  wrote raw response to {pool['raw_file']}")

        if result.get("state") != "QUERY_STATE_COMPLETED":
            print(f"  FAILED: {result.get('state')}")
            print(json.dumps(result.get("error", result), indent=2))
            continue

        rows = result["result"]["rows"]
        metadata = result["result"]["metadata"]
        print(f"  rows={len(rows)}  execution_time_ms={metadata.get('execution_time_millis')}")
        pool_row_counts[pool["name"]] = len(rows)

        nan_count = 0
        for row in rows:
            hour = row["hour"]  # e.g. "2023-03-11 07:00:00.000 UTC"
            dt = hour.split(" ")[0]
            pair = row["pair"]
            trade_count = row["trade_count"]
            volume_usd = row["volume_usd"]
            raw_price = row.get("implied_price")
            price = as_finite_float(raw_price)

            if price is None:
                nan_count += 1
                is_valid = "false"
                anomaly = "NAN_PRICE" if raw_price is not None else "ZERO_AMOUNT_LEG"
                price_out = "\\N"  # Hive NULL in TEXTFILE
            else:
                is_valid = "true"
                anomaly = "NONE"
                price_out = repr(price)

            staging_rows.append("\t".join([
                hour.replace(" UTC", ""),           # window_start_ts
                pool["project"],                     # project
                pool["pool_address"],                # pool_address
                "ethereum",                           # blockchain
                str(trade_count),                     # trade_count
                repr(volume_usd) if volume_usd is not None else "\\N",  # volume_usd
                price_out,                             # implied_price
                str(raw_price),                        # raw_price_value
                is_valid,                              # is_valid_price
                anomaly,                               # anomaly_flag
                "dune",                                # source
                "\\N",                                  # ingested_at (set at load time)
                pair,                                   # pair (partition)
                dt,                                     # dt (partition)
            ]))
        print(f"  NaN/invalid price rows: {nan_count}\n")

    STAGING_FILE.write_text("\n".join(staging_rows) + "\n")
    print(f"Wrote {len(staging_rows)} staging rows to {STAGING_FILE}")

    usage_after = get_usage(api_key)
    credits_used_this_run = usage_after["credits_used"] - usage_before["credits_used"]
    print(f"\nCredits after: {usage_after['credits_used']} / {usage_after['credits_included']}")
    print(f"Credits consumed by this backfill: {credits_used_this_run:.4f}")
    print(f"\nRow counts per pool: {json.dumps(pool_row_counts, indent=2)}")


if __name__ == "__main__":
    main()
