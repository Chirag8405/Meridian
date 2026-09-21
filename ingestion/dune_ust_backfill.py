"""
Historical backfill for the May 2022 TerraUSD (UST) depeg — additive to
dune_backfill.py, does not touch the existing USDC/USDT/DAI data.

Pool: Curve UST MetaPool, 0x890f4e345B1dAED0367A877a1612f86A1f86985f.
Verified on-chain (not assumed from memory): eth_getCode confirms a real
contract, and coins(0)/coins(1) decode to UST and 3Crv (the Curve 3pool LP
token) respectively — this is a metapool, UST paired against 3pool's LP
token, not against any single stablecoin directly.

Confirmed queryable via Dune's dex.trades (47,097 total trades indexed,
2020-12-19 to present — not deprecated/delisted).

Schema decision (flagged and confirmed with the user before implementing):
Dune's dex.trades already decomposes this metapool's trades into two
levels — wrapped (UST<->3Crv, via Curve's exchange()) and underlying
(UST<->DAI, UST<->USDC, UST<->USDT, via Curve's exchange_underlying()).
Using the three underlying-level pairs: they fit the EXISTING pair-of-two-
stablecoins schema in hive/schema.sql exactly (pair is just a STRING
partition column — UST_USDC/UST_USDT/UST_DAI are new values, not new
structure), and give directly comparable coverage against all three
underlying assets rather than a single basket-asset proxy.

Window: 2022-04-15 to 2022-06-15 UTC — lead-up, the depeg itself
(~May 9-13), and the failed recovery attempts that followed.
"""

import json
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
STAGING_FILE = PROJECT_ROOT / "data" / "processed" / "stablecoin_pool_hourly_ust_backfill.tsv"

DUNE_API_BASE = "https://api.dune.com/api/v1"

UST_METAPOOL_ADDRESS = "0x890f4e345B1dAED0367A877a1612f86A1f86985f"

BACKFILL_START = "2022-04-15 00:00:00"
BACKFILL_END = "2022-06-15 00:00:00"

UST_SQL = f"""
WITH ust_trades AS (
  SELECT block_time, token_sold_symbol, token_bought_symbol,
         token_sold_amount, token_bought_amount, amount_usd
  FROM dex.trades
  WHERE blockchain = 'ethereum'
    AND project_contract_address = {UST_METAPOOL_ADDRESS}
    AND block_time >= TIMESTAMP '{BACKFILL_START}'
    AND block_time < TIMESTAMP '{BACKFILL_END}'
)
SELECT date_trunc('hour', block_time) AS hour, 'UST_USDC' AS pair,
  count(*) AS trade_count, sum(amount_usd) AS volume_usd,
  avg(CASE
        WHEN token_sold_symbol = 'UST' AND token_bought_symbol = 'USDC'
          THEN token_bought_amount / token_sold_amount
        WHEN token_sold_symbol = 'USDC' AND token_bought_symbol = 'UST'
          THEN token_sold_amount / token_bought_amount
      END) AS implied_price
FROM ust_trades
WHERE (token_sold_symbol = 'UST' AND token_bought_symbol = 'USDC')
   OR (token_sold_symbol = 'USDC' AND token_bought_symbol = 'UST')
GROUP BY 1
UNION ALL
SELECT date_trunc('hour', block_time) AS hour, 'UST_USDT' AS pair,
  count(*) AS trade_count, sum(amount_usd) AS volume_usd,
  avg(CASE
        WHEN token_sold_symbol = 'UST' AND token_bought_symbol = 'USDT'
          THEN token_bought_amount / token_sold_amount
        WHEN token_sold_symbol = 'USDT' AND token_bought_symbol = 'UST'
          THEN token_sold_amount / token_bought_amount
      END) AS implied_price
FROM ust_trades
WHERE (token_sold_symbol = 'UST' AND token_bought_symbol = 'USDT')
   OR (token_sold_symbol = 'USDT' AND token_bought_symbol = 'UST')
GROUP BY 1
UNION ALL
SELECT date_trunc('hour', block_time) AS hour, 'UST_DAI' AS pair,
  count(*) AS trade_count, sum(amount_usd) AS volume_usd,
  avg(CASE
        WHEN token_sold_symbol = 'UST' AND token_bought_symbol = 'DAI'
          THEN token_bought_amount / token_sold_amount
        WHEN token_sold_symbol = 'DAI' AND token_bought_symbol = 'UST'
          THEN token_sold_amount / token_bought_amount
      END) AS implied_price
FROM ust_trades
WHERE (token_sold_symbol = 'UST' AND token_bought_symbol = 'DAI')
   OR (token_sold_symbol = 'DAI' AND token_bought_symbol = 'UST')
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


def get_usage(api_key: str) -> dict:
    resp = requests.post(
        f"{DUNE_API_BASE}/usage",
        headers={"X-Dune-Api-Key": api_key, "Content-Type": "application/json"},
        json={}, timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["billing_periods"][0]


def execute_sql(api_key: str, sql: str) -> str:
    resp = requests.post(
        f"{DUNE_API_BASE}/sql/execute",
        headers={"X-Dune-Api-Key": api_key, "Content-Type": "application/json"},
        json={"sql": sql, "performance": "medium"}, timeout=30,
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

    execution_id = execute_sql(api_key, UST_SQL)
    print(f"execution_id={execution_id}, polling...")
    result = poll_until_done(api_key, execution_id)

    raw_file = RAW_DIR / "dune_backfill_ust_metapool.json"
    raw_file.write_text(json.dumps(result, indent=2))
    print(f"wrote raw response to {raw_file}")

    if result.get("state") != "QUERY_STATE_COMPLETED":
        print(f"FAILED: {result.get('state')}")
        print(json.dumps(result.get("error", result), indent=2))
        sys.exit(1)

    rows = result["result"]["rows"]
    metadata = result["result"]["metadata"]
    print(f"rows={len(rows)}  execution_time_ms={metadata.get('execution_time_millis')}")

    pair_counts = {}
    staging_rows = []
    nan_count = 0
    zero_value_count = 0

    for row in rows:
        hour = row["hour"]
        dt = hour.split(" ")[0]
        pair = row["pair"]
        pair_counts[pair] = pair_counts.get(pair, 0) + 1
        trade_count = row["trade_count"]
        volume_usd = row["volume_usd"]
        raw_price = row.get("implied_price")
        price = as_finite_float(raw_price)

        if price is None:
            nan_count += 1
            is_valid = "false"
            anomaly = "NAN_PRICE" if raw_price is not None else "ZERO_AMOUNT_LEG"
            price_out = "\\N"
        elif price == 0.0 and (volume_usd or 0.0) == 0.0:
            # Same ZERO_VALUE_TRADE check as dune_backfill.py — a real
            # trade executed at a genuinely zero/dust value, not a
            # calculation error. Exact 0.0 only. This is the exact
            # condition that found 221 rows in the original UST backfill
            # (before this check existed) and none in the calm data.
            zero_value_count += 1
            is_valid = "false"
            anomaly = "ZERO_VALUE_TRADE"
            price_out = "\\N"
        else:
            is_valid = "true"
            anomaly = "NONE"
            price_out = repr(price)

        staging_rows.append("\t".join([
            hour.replace(" UTC", ""),
            "curve",
            UST_METAPOOL_ADDRESS,
            "ethereum",
            str(trade_count),
            repr(volume_usd) if volume_usd is not None else "\\N",
            price_out,
            str(raw_price),
            is_valid,
            anomaly,
            "dune",
            "\\N",
            pair,
            dt,
        ]))

    STAGING_FILE.write_text("\n".join(staging_rows) + "\n")
    print(f"Wrote {len(staging_rows)} staging rows to {STAGING_FILE}")
    print(f"NaN/invalid price rows: {nan_count}")
    print(f"Zero-value trade rows: {zero_value_count}")
    print(f"Row counts per pair: {json.dumps(pair_counts, indent=2)}")

    usage_after = get_usage(api_key)
    credits_used_this_run = usage_after["credits_used"] - usage_before["credits_used"]
    print(f"\nCredits after: {usage_after['credits_used']} / {usage_after['credits_included']}")
    print(f"Credits consumed by this backfill: {credits_used_this_run:.4f}")


if __name__ == "__main__":
    main()
