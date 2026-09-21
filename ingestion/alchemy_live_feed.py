"""
Live on-chain feed test via Alchemy WebSocket — NOT the production streaming
ingestion pipeline. Validates that we can decode live pool events correctly
before designing the Spark Structured Streaming consumer around it.

Subscribes to two pools on Ethereum mainnet:
  - Curve 3pool (DAI/USDC/USDT): 0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7
    (same pool the Dune historical backfill uses — confirmed from the earlier
    Dune query in ingestion/dune_test_pull.py)
  - Uniswap V2 USDC/USDT pool:   0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f

IMPORTANT PROTOCOL DIFFERENCE (flagging, since the request assumed uniform
Sync+Swap events across both pools):
  Uniswap V2 pools emit two distinct events: `Sync` (reserve0/reserve1 after
  every state change) and `Swap` (per-trade amounts). Curve pools do NOT have
  a `Sync` event at all — that's Uniswap-V2-specific terminology for its
  cached-reserve model. Curve's swap event is `TokenExchange`, and it has no
  event that fires purely on reserve/balance changes. To still get a
  reserve-snapshot signal for Curve (informative for the same "is liquidity
  draining" question Sync answers on Uniswap), this script calls the
  contract's `balances(i)` view function right after each TokenExchange event
  and emits it as a separate synthetic record with
  event_type='RESERVE_SNAPSHOT' rather than pretending it's a real Sync event.

Raw per-event records are written to data/raw/alchemy_live_test.jsonl (one
JSON object per line). This is intentionally NOT the same shape as the Hive
table in hive/schema.sql, which stores hourly aggregates — these are
individual on-chain events. A later Spark Streaming job aggregates these into
the same hourly-bucket shape (trade_count, volume_usd, implied_price per
hour) before it lands in that table; see field-mapping notes at the bottom of
this file.
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import websockets
from eth_abi import decode as abi_decode
from eth_utils import keccak, to_checksum_address

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
OUTPUT_FILE = PROJECT_ROOT / "data" / "raw" / "alchemy_live_test.jsonl"

CURVE_3POOL_ADDRESS = to_checksum_address("0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7")
UNISWAP_V2_USDC_USDT_ADDRESS = to_checksum_address("0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f")

# Curve 3pool's fixed token composition (DAI, USDC, USDT in that index order)
# — this is the pool's known, unchanging deployment configuration, not
# something we're guessing at runtime.
CURVE_3POOL_TOKENS = [
    {"symbol": "DAI", "decimals": 18},
    {"symbol": "USDC", "decimals": 6},
    {"symbol": "USDT", "decimals": 6},
]

TOPIC_SYNC = "0x" + keccak(text="Sync(uint112,uint112)").hex()
TOPIC_SWAP_V2 = "0x" + keccak(text="Swap(address,uint256,uint256,uint256,uint256,address)").hex()
TOPIC_TOKEN_EXCHANGE = "0x" + keccak(text="TokenExchange(address,int128,uint256,int128,uint256)").hex()

ERC20_DECIMALS_SELECTOR = "0x313ce567"  # decimals()
UNISWAP_TOKEN0_SELECTOR = "0x0dfe1681"  # token0()
UNISWAP_TOKEN1_SELECTOR = "0xd21220a7"  # token1()
CURVE_BALANCES_SELECTOR = "0x4903b0d1"  # balances(uint256)

TEST_DURATION_SECONDS = 600


def load_api_key() -> str:
    if not ENV_FILE.exists():
        sys.exit(f"Missing {ENV_FILE} — see .env.example")
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("ALCHEMY_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    sys.exit("ALCHEMY_API_KEY not set in .env")


def eth_call(http_url: str, to_address: str, data: str) -> str:
    resp = requests.post(
        http_url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to_address, "data": data}, "latest"],
        },
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"eth_call error: {body['error']}")
    return body["result"]


def fetch_uniswap_v2_pool_metadata(http_url: str, pool_address: str) -> dict:
    """Fetch token0/token1 addresses and decimals dynamically rather than
    assuming an order — Uniswap V2 orders tokens by contract address, and
    guessing wrong silently swaps every price by its reciprocal."""
    token0 = "0x" + eth_call(http_url, pool_address, UNISWAP_TOKEN0_SELECTOR)[-40:]
    token1 = "0x" + eth_call(http_url, pool_address, UNISWAP_TOKEN1_SELECTOR)[-40:]
    dec0 = int(eth_call(http_url, token0, ERC20_DECIMALS_SELECTOR), 16)
    dec1 = int(eth_call(http_url, token1, ERC20_DECIMALS_SELECTOR), 16)
    return {
        "token0": to_checksum_address(token0),
        "token1": to_checksum_address(token1),
        "decimals0": dec0,
        "decimals1": dec1,
    }


def fetch_curve_balances(http_url: str, pool_address: str) -> list[int]:
    balances = []
    for i in range(len(CURVE_3POOL_TOKENS)):
        data = CURVE_BALANCES_SELECTOR + f"{i:064x}"
        raw = eth_call(http_url, pool_address, data)
        balances.append(int(raw, 16))
    return balances


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_ratio(numerator: float, denominator: float):
    """Returns (implied_price, is_valid_price, anomaly_flag, raw_note)."""
    if denominator == 0:
        return None, False, "ZERO_AMOUNT_LEG", f"denominator=0 (numerator={numerator})"
    price = numerator / denominator
    if price != price or abs(price) == float("inf"):  # NaN/Inf check
        return None, False, "NAN_PRICE", str(price)
    if price == 0.0:
        # numerator was exactly 0 despite a nonzero denominator: a real
        # trade/reserve state, but a genuinely zero/dust value — not a
        # calculation error (that's NAN_PRICE), a real zero. Same
        # ZERO_VALUE_TRADE treatment as the Dune backfill scripts: not a
        # usable price, but not dropped either. Exact 0.0 only.
        return None, False, "ZERO_VALUE_TRADE", "0.0"
    return price, True, "NONE", None


class RecordWriter:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a")
        self.count = 0

    def write(self, record: dict):
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()
        self.count += 1

    def close(self):
        self._fh.close()


def decode_uniswap_sync(log: dict, meta: dict) -> dict:
    reserve0, reserve1 = abi_decode(["uint112", "uint112"], bytes.fromhex(log["data"][2:]))
    r0 = reserve0 / (10 ** meta["decimals0"])
    r1 = reserve1 / (10 ** meta["decimals1"])
    # implied_price defined as token1-per-token0, matching the Dune
    # convention of "quote per base" (e.g. usdc_per_usdt_implied_price)
    price, is_valid, anomaly, raw_note = safe_ratio(r0, r1)
    return {
        "reserve0": r0,
        "reserve1": r1,
        "implied_price": price,
        "is_valid_price": is_valid,
        "anomaly_flag": anomaly,
        "raw_price_value": raw_note if raw_note else str(price),
    }


def decode_uniswap_swap(log: dict, meta: dict) -> dict:
    """
    Uniswap V2's Swap event fires once per call to the pair's swap()
    function, and amount{0,1}{In,Out} are derived purely from comparing the
    pair's token balances before/after the call — NOT from any declared
    trade "intent". A normal router multi-hop trade fires a SEPARATE Swap
    event per pool it touches (confirmed: this is not why dual-sided legs
    appear here), so a single event with both amount0In>0 and amount1In>0
    (or both amount0Out>0 and amount1Out>0) means something more complex
    than a plain A-for-B swap happened in the same call — observed in
    practice on a real dual-leg example (tx 0xe5b9b8b3...) that turned out
    to be a smart-order-router transaction also touching Uniswap V4 in the
    same tx, where cross-protocol balance interactions bled into how this
    pool's own balance delta was computed.

    Picking whichever leg looks "dominant" and computing price from it
    alone understates the real deviation: on that example, dominant-leg
    picking gave 1.0012 (0.12% off parity) while netting the true effective
    flow gives 1.0194 (1.94% off) — the dominant-leg number silently hid an
    ~16x larger price move. So: compute price from NET effective flow
    (amountIn - amountOut per side), and flag raw dual-sided-leg events with
    anomaly_flag='MULTI_LEG_TRADE' regardless of whether netting resolves
    to a valid price, so they're queryable/excludable rather than silently
    blended into clean single-hop data.
    """
    amount0_in, amount1_in, amount0_out, amount1_out = abi_decode(
        ["uint256", "uint256", "uint256", "uint256"], bytes.fromhex(log["data"][2:])
    )
    is_multi_leg = (
        (amount0_in > 0 and amount1_in > 0)
        or (amount0_out > 0 and amount1_out > 0)
    )

    net0 = amount0_in - amount0_out  # >0: net token0 sold to pool; <0: net bought
    net1 = amount1_in - amount1_out

    if net0 > 0 and net1 < 0:
        sold0_adj = net0 / (10 ** meta["decimals0"])
        bought1_adj = -net1 / (10 ** meta["decimals1"])
        price, is_valid, anomaly, raw_note = safe_ratio(sold0_adj, bought1_adj)
    elif net1 > 0 and net0 < 0:
        sold1_adj = net1 / (10 ** meta["decimals1"])
        bought0_adj = -net0 / (10 ** meta["decimals0"])
        price, is_valid, anomaly, raw_note = safe_ratio(bought0_adj, sold1_adj)
    elif net0 == 0 and net1 == 0:
        # No net movement at all — a genuine zero-amount/ghost event, not
        # an ambiguous-direction one.
        price, is_valid, anomaly, raw_note = (
            None, False, "ZERO_AMOUNT_LEG", "net0=0 and net1=0 after netting"
        )
    else:
        # Shouldn't happen under the AMM invariant (nets can't legitimately
        # share a sign), but guarded rather than silently mis-priced.
        price, is_valid, anomaly, raw_note = (
            None, False, "AMBIGUOUS_NET_DIRECTION", f"net0={net0} net1={net1}"
        )

    if is_multi_leg and anomaly == "NONE":
        anomaly = "MULTI_LEG_TRADE"

    a0in = amount0_in / (10 ** meta["decimals0"])
    a1in = amount1_in / (10 ** meta["decimals1"])
    a0out = amount0_out / (10 ** meta["decimals0"])
    a1out = amount1_out / (10 ** meta["decimals1"])
    return {
        "amount0_in": a0in, "amount1_in": a1in,
        "amount0_out": a0out, "amount1_out": a1out,
        "is_multi_leg": is_multi_leg,
        "implied_price": price,
        "is_valid_price": is_valid,
        "anomaly_flag": anomaly,
        "raw_price_value": raw_note if raw_note else str(price),
    }


def decode_curve_token_exchange(log: dict) -> dict:
    sold_id, tokens_sold, bought_id, tokens_bought = abi_decode(
        ["int128", "uint256", "int128", "uint256"], bytes.fromhex(log["data"][2:])
    )
    sold_tok = CURVE_3POOL_TOKENS[sold_id]
    bought_tok = CURVE_3POOL_TOKENS[bought_id]
    sold_adj = tokens_sold / (10 ** sold_tok["decimals"])
    bought_adj = tokens_bought / (10 ** bought_tok["decimals"])
    price, is_valid, anomaly, raw_note = safe_ratio(bought_adj, sold_adj)
    return {
        "sold_symbol": sold_tok["symbol"], "sold_amount": sold_adj,
        "bought_symbol": bought_tok["symbol"], "bought_amount": bought_adj,
        "implied_price": price,
        "is_valid_price": is_valid,
        "anomaly_flag": anomaly,
        "raw_price_value": raw_note if raw_note else str(price),
    }


async def run(api_key: str, writer: RecordWriter):
    ws_url = f"wss://eth-mainnet.g.alchemy.com/v2/{api_key}"
    http_url = f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"

    print("Fetching Uniswap V2 pool metadata (token0/token1, decimals)...")
    uni_meta = fetch_uniswap_v2_pool_metadata(http_url, UNISWAP_V2_USDC_USDT_ADDRESS)
    print(f"  token0={uni_meta['token0']} (decimals={uni_meta['decimals0']})")
    print(f"  token1={uni_meta['token1']} (decimals={uni_meta['decimals1']})")

    decode_errors = []
    event_counts = {}

    async with websockets.connect(ws_url) as ws:
        subs = [
            {
                "id": 1,
                "method": "eth_subscribe",
                "params": ["logs", {
                    "address": CURVE_3POOL_ADDRESS,
                    "topics": [TOPIC_TOKEN_EXCHANGE],
                }],
            },
            {
                "id": 2,
                "method": "eth_subscribe",
                "params": ["logs", {
                    "address": UNISWAP_V2_USDC_USDT_ADDRESS,
                    "topics": [[TOPIC_SYNC, TOPIC_SWAP_V2]],
                }],
            },
        ]
        sub_id_to_pool = {}
        for req in subs:
            await ws.send(json.dumps(req))
            resp = json.loads(await ws.recv())
            sub_id_to_pool[resp["result"]] = (
                "curve_3pool" if req["id"] == 1 else "uniswap_v2_usdc_usdt"
            )
            print(f"Subscribed: {sub_id_to_pool[resp['result']]} -> {resp['result']}")

        print(f"\nListening for {TEST_DURATION_SECONDS}s...\n")
        deadline = time.time() + TEST_DURATION_SECONDS
        while time.time() < deadline:
            timeout = deadline - time.time()
            if timeout <= 0:
                break
            try:
                raw_msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            except asyncio.TimeoutError:
                break

            msg = json.loads(raw_msg)
            if msg.get("method") != "eth_subscription":
                continue
            sub_id = msg["params"]["subscription"]
            pool_name = sub_id_to_pool.get(sub_id, "unknown")
            log = msg["params"]["result"]
            topic0 = log["topics"][0]

            base_record = {
                "received_at": now_iso(),
                "block_number": int(log["blockNumber"], 16),
                "tx_hash": log["transactionHash"],
                "log_index": int(log["logIndex"], 16),
                "pool_address": log["address"],
                "pool_name": pool_name,
                "blockchain": "ethereum",
                "source": "alchemy_live",
            }

            try:
                if pool_name == "curve_3pool" and topic0.lower() == TOPIC_TOKEN_EXCHANGE.lower():
                    decoded = decode_curve_token_exchange(log)
                    record = {**base_record, "project": "curve", "event_type": "SWAP", **decoded}
                    writer.write(record)
                    event_counts["curve.SWAP"] = event_counts.get("curve.SWAP", 0) + 1

                    # Synthesize a reserve-snapshot record (Curve has no
                    # native Sync event — see module docstring)
                    balances = fetch_curve_balances(http_url, CURVE_3POOL_ADDRESS)
                    dai_bal = balances[0] / (10 ** CURVE_3POOL_TOKENS[0]["decimals"])
                    usdc_bal = balances[1] / (10 ** CURVE_3POOL_TOKENS[1]["decimals"])
                    usdt_bal = balances[2] / (10 ** CURVE_3POOL_TOKENS[2]["decimals"])
                    price, is_valid, anomaly, raw_note = safe_ratio(usdc_bal, usdt_bal)
                    snapshot_record = {
                        **base_record,
                        "project": "curve",
                        "event_type": "RESERVE_SNAPSHOT",
                        "dai_balance": dai_bal,
                        "usdc_balance": usdc_bal,
                        "usdt_balance": usdt_bal,
                        "implied_price": price,
                        "is_valid_price": is_valid,
                        "anomaly_flag": anomaly,
                        "raw_price_value": raw_note if raw_note else str(price),
                    }
                    writer.write(snapshot_record)
                    event_counts["curve.RESERVE_SNAPSHOT"] = event_counts.get("curve.RESERVE_SNAPSHOT", 0) + 1

                elif pool_name == "uniswap_v2_usdc_usdt" and topic0.lower() == TOPIC_SYNC.lower():
                    decoded = decode_uniswap_sync(log, uni_meta)
                    record = {**base_record, "project": "uniswap_v2", "event_type": "SYNC", **decoded}
                    writer.write(record)
                    event_counts["uniswap.SYNC"] = event_counts.get("uniswap.SYNC", 0) + 1

                elif pool_name == "uniswap_v2_usdc_usdt" and topic0.lower() == TOPIC_SWAP_V2.lower():
                    decoded = decode_uniswap_swap(log, uni_meta)
                    record = {**base_record, "project": "uniswap_v2", "event_type": "SWAP", **decoded}
                    writer.write(record)
                    event_counts["uniswap.SWAP"] = event_counts.get("uniswap.SWAP", 0) + 1

                else:
                    decode_errors.append(f"Unrecognized topic0={topic0} on {pool_name}")

            except Exception as e:
                decode_errors.append(f"{pool_name} decode error: {e!r} (tx={log['transactionHash']})")

    print("=== EVENT COUNTS ===")
    for k, v in event_counts.items():
        print(f"  {k}: {v}")
    if decode_errors:
        print(f"\n=== DECODE ERRORS ({len(decode_errors)}) ===")
        for e in decode_errors:
            print(f"  {e}")
    else:
        print("\nNo decode errors.")


def main():
    api_key = load_api_key()
    writer = RecordWriter(OUTPUT_FILE)
    try:
        asyncio.run(run(api_key, writer))
    finally:
        writer.close()
        print(f"\nWrote {writer.count} records to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

# --- Field mapping to hive/schema.sql (for the later Spark Streaming job) ---
# A Spark Streaming aggregation job (not built yet) will roll these per-event
# JSONL records up into hourly buckets matching meridian.stablecoin_pool_hourly:
#   window_start_ts  <- floor(received_at / block_time, 1 hour)
#   project           <- project (as-is: 'curve', 'uniswap_v2')
#   pool_address       <- pool_address (as-is)
#   blockchain          <- blockchain (as-is)
#   trade_count          <- count(*) WHERE event_type='SWAP' per hour
#   volume_usd             <- needs a USD price join (not computed live here —
#                             these records store implied token-pair ratios,
#                             not USD volume; that join happens in Spark)
#   implied_price            <- avg(implied_price) per hour (or last SYNC/
#                             RESERVE_SNAPSHOT value, depending on which
#                             signal the streaming design prefers)
#   is_valid_price             <- all(is_valid_price) per hour, or per-row
#                             passthrough if the Hive table moves to
#                             per-event grain instead of hourly
#   anomaly_flag                 <- any non-'NONE' flag in the hour, surfaced
#                             rather than dropped, same as the historical data
#   raw_price_value               <- kept per-event only (not meaningful
#                             aggregated); would need its own event-grain
#                             table if per-event auditability matters live
#   source                          <- 'alchemy_live' (vs 'dune' for the
#                             historical backfill) — this is the column that
#                             lets both sources coexist in one table
