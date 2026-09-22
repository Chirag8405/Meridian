"""
Production Alchemy WebSocket live feed for the Spark Structured Streaming
consumer (spark/stream_alchemy_live.scala). Evolved from an earlier
short-duration decode-validation test script — the decode/anomaly-flag
logic below (decode_uniswap_sync, decode_uniswap_swap,
decode_curve_token_exchange, safe_ratio) is UNCHANGED from that script,
reused verbatim rather than reimplemented, per the confirmed design.

Design decided and confirmed with the user before writing this (see
FINDINGS.md / ARCHITECTURE.md for the full live-streaming design report) —
not written speculatively. Key points that shaped this rewrite:

- Runs INDEFINITELY (not the old fixed TEST_DURATION_SECONDS test run),
  meant to be supervised by a systemd --user service (see
  systemd/meridian-live-feed.service), not a one-shot nohup job.
- Tracks 4 pools for parity with the historical backfill: Curve 3pool
  (covers USDC_USDT + USDC_DAI in one contract) + Uniswap V2 USDC_USDT +
  Uniswap V2 USDC_DAI (address already known from ingestion/dune_backfill.py,
  just not previously subscribed to here).
- Direct DAI<->USDT Curve swaps (no USDC leg) are decoded and WRITTEN (never
  silently dropped, same ethos as every other anomaly in this project) but
  tagged pair=null — the historical dataset never tracked a USDT_DAI pair,
  so this keeps live ingestion scope-consistent with what already exists
  rather than inventing an untracked pair. The Spark aggregation job filters
  on pair IS NOT NULL.
- Reconnect with backoff: a WebSocket subscription does not replay missed
  events — a machine sleep/disconnect of hours+ WILL lose events from the
  push stream. On reconnect, gap-filled via eth_getLogs for the missed
  block range, tagged source='alchemy_getlogs_replay' (vs 'alchemy_live'
  for genuine real-time push events) so the two are distinguishable
  downstream. Last-processed block is persisted to STATE_FILE so this
  works across process restarts, not just in-process reconnects.
- Writes small, atomically-renamed JSON files into a landing directory
  (OUTPUT_DIR) rather than one ever-growing appended file — required by
  Spark Structured Streaming's File source, which expects complete,
  immutable files to appear, not a file that's still being written to.
- USD volume: historical volume_usd came from Dune's own real market-price
  valuation; live on-chain events only give token-to-token ratios. Fetches
  a live USD reference price per stablecoin from CoinGecko's keyless public
  API (no API key needed at this call volume — confirmed via CoinGecko
  docs) rather than naively assuming 1 stablecoin == $1, which would be
  wrong exactly during an active depeg.
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
import websockets
from eth_abi import decode as abi_decode
from eth_utils import keccak, to_checksum_address

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "alchemy_live_stream"
STATE_FILE = PROJECT_ROOT / "data" / "raw" / "alchemy_live_stream_state.json"

CURVE_3POOL_ADDRESS = to_checksum_address("0xbEbc44782C7dB0a1A60Cb6fe97d0b483032FF1C7")
UNISWAP_V2_USDC_USDT_ADDRESS = to_checksum_address("0x3041CbD36888bECc7bbCBc0045E3B1f144466f5f")
UNISWAP_V2_USDC_DAI_ADDRESS = to_checksum_address("0xAe461cA67B15dc8dc81CE7615e0320Da1A9aB8D5")

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

RECONNECT_BACKOFF_SECS = [5, 15, 30, 60, 120, 300]  # caps at 5 min
FILE_ROLLOVER_SECS = 300  # new landing file at most every 5 minutes
COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_IDS = {"USDC": "usd-coin", "USDT": "tether", "DAI": "dai"}
PRICE_CACHE_TTL_SECS = 60


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


def eth_block_number(http_url: str) -> int:
    resp = requests.post(
        http_url,
        json={"jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": []},
        timeout=15,
    )
    resp.raise_for_status()
    return int(resp.json()["result"], 16)


_block_ts_cache: dict[int, str] = {}


def eth_block_timestamp(http_url: str, block_number: int) -> str:
    """The actual on-chain block timestamp, as an ISO string — NOT the same
    as received_at. For a live push event the two are seconds apart and it
    barely matters, but for a gap-filled event (recovered via eth_getLogs
    possibly hours or days after it happened) received_at reflects when the
    catch-up script happened to run, not when the trade occurred. Using
    received_at for hourly bucketing would put gap-filled historical trades
    in the wrong hour. Cached per block_number since many events in a
    gap-fill run share the same or nearby blocks."""
    if block_number in _block_ts_cache:
        return _block_ts_cache[block_number]
    resp = requests.post(
        http_url,
        json={"jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber",
              "params": [hex(block_number), False]},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()
    if "error" in body or not body.get("result"):
        raise RuntimeError(f"eth_getBlockByNumber error for block {block_number}: {body.get('error')}")
    ts_unix = int(body["result"]["timestamp"], 16)
    ts_iso = datetime.fromtimestamp(ts_unix, tz=timezone.utc).isoformat()
    _block_ts_cache[block_number] = ts_iso
    return ts_iso


ETH_GETLOGS_MAX_BLOCK_RANGE = 10  # Alchemy free tier hard limit, confirmed
# empirically: a >10-block range returns HTTP 400 with error code -32600
# ("Under the Free tier plan, you can make eth_getLogs requests with up to
# a 10 block range"). Gap-fill exists specifically to recover from hours+
# of downtime (thousands of blocks at ~12s/block), so chunking this is
# required for the feature to work at all, not an edge case.


def _eth_get_logs_single(http_url: str, address: str, topics: list, from_block: int, to_block: int) -> list:
    resp = requests.post(
        http_url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getLogs",
            "params": [{
                "address": address,
                "topics": topics,
                "fromBlock": hex(from_block),
                "toBlock": hex(to_block),
            }],
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"eth_getLogs error: {body['error']}")
    return body["result"]


def eth_get_logs(http_url: str, address: str, topics: list, from_block: int, to_block: int) -> list:
    """Chunks the request into ETH_GETLOGS_MAX_BLOCK_RANGE-block windows to
    stay under Alchemy's free-tier range limit. A large gap (e.g. an 8-hour
    sleep ~= 2400 blocks) means hundreds of chunked calls — a small delay
    between them avoids tripping Alchemy's separate per-second rate limit."""
    results = []
    chunk_start = from_block
    while chunk_start <= to_block:
        chunk_end = min(chunk_start + ETH_GETLOGS_MAX_BLOCK_RANGE - 1, to_block)
        results.extend(_eth_get_logs_single(http_url, address, topics, chunk_start, chunk_end))
        chunk_start = chunk_end + 1
        if chunk_start <= to_block:
            time.sleep(0.15)
    return results


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
    """Returns (implied_price, is_valid_price, anomaly_flag, raw_note).
    UNCHANGED from the earlier validated version — reused, not reimplemented."""
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


class PriceCache:
    """Live USD reference price per stablecoin, from CoinGecko's keyless
    public API (no key needed at this call volume). TTL-cached so we don't
    exceed the keyless rate limit (5-15 calls/min) — one call covers all
    three symbols since CoinGecko's endpoint takes a comma-separated list."""

    def __init__(self):
        self._prices = {"USDC": 1.0, "USDT": 1.0, "DAI": 1.0}  # safe fallback
        self._fetched_at = 0.0

    def get(self, symbol: str) -> float:
        if time.time() - self._fetched_at > PRICE_CACHE_TTL_SECS:
            self._refresh()
        return self._prices.get(symbol, 1.0)

    def _refresh(self):
        try:
            ids = ",".join(COINGECKO_IDS.values())
            resp = requests.get(
                COINGECKO_URL, params={"ids": ids, "vs_currencies": "usd"}, timeout=10
            )
            resp.raise_for_status()
            body = resp.json()
            for symbol, cg_id in COINGECKO_IDS.items():
                if cg_id in body and "usd" in body[cg_id]:
                    self._prices[symbol] = float(body[cg_id]["usd"])
            self._fetched_at = time.time()
        except Exception as e:
            # Keep the last-known (or fallback $1.00) prices rather than
            # crashing the whole feed over a transient pricing-API hiccup —
            # a stale/fallback price is a degraded signal, not a fatal one.
            print(f"[price_cache] refresh failed, keeping last-known prices: {e!r}")


class RolloverWriter:
    """Writes decoded records to small, atomically-renamed JSON files in a
    landing directory — Spark Structured Streaming's File source requires
    complete, immutable files to appear (not one file that's still being
    appended to), confirmed against Spark's docs before designing this."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._buffer = []
        self._rollover_at = time.time() + FILE_ROLLOVER_SECS
        self.count = 0

    def write(self, record: dict):
        self._buffer.append(record)
        self.count += 1
        if time.time() >= self._rollover_at or len(self._buffer) >= 500:
            self.flush()

    def flush(self):
        if not self._buffer:
            self._rollover_at = time.time() + FILE_ROLLOVER_SECS
            return
        final_name = f"events_{int(time.time())}_{uuid.uuid4().hex[:8]}.json"
        tmp_path = self.out_dir / f".{final_name}.tmp"
        final_path = self.out_dir / final_name
        with open(tmp_path, "w") as fh:
            for rec in self._buffer:
                fh.write(json.dumps(rec) + "\n")
        os.rename(tmp_path, final_path)  # atomic on the same filesystem
        self._buffer = []
        self._rollover_at = time.time() + FILE_ROLLOVER_SECS


class StreamState:
    """Persists the last-processed block number across process restarts,
    so a reconnect (in-process) or a relaunch (after a crash/reboot) both
    know where to resume the eth_getLogs gap-fill from."""

    def __init__(self, path: Path):
        self.path = path
        self.last_block = 0
        if path.exists():
            try:
                self.last_block = json.loads(path.read_text()).get("last_block", 0)
            except Exception:
                pass

    def update(self, block_number: int):
        if block_number > self.last_block:
            self.last_block = block_number
            self.path.write_text(json.dumps({"last_block": self.last_block}))


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
    UNCHANGED from the earlier validated version — reused, not reimplemented.
    See the original module's docstring history for the multi-leg netting
    rationale (a real traced transaction showed dominant-leg picking
    understates price deviation by ~16x); net-flow-based pricing plus
    MULTI_LEG_TRADE/AMBIGUOUS_NET_DIRECTION anomaly flags fixed that.
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
        price, is_valid, anomaly, raw_note = (
            None, False, "ZERO_AMOUNT_LEG", "net0=0 and net1=0 after netting"
        )
    else:
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
    """UNCHANGED from the earlier validated version — reused, not reimplemented."""
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


def curve_pair_for(sold_symbol: str, bought_symbol: str) -> str | None:
    """The historical dataset only ever tracked USDC_USDT and USDC_DAI (never
    USDT_DAI) — a direct DAI<->USDT Curve swap doesn't touch USDC at all, so
    it has no historical counterpart pair. Returns None for that case rather
    than inventing a new pair; the record is still written (see module
    docstring), just filtered out of pair-level aggregation downstream."""
    legs = {sold_symbol, bought_symbol}
    if legs == {"USDC", "USDT"}:
        return "USDC_USDT"
    if legs == {"USDC", "DAI"}:
        return "USDC_DAI"
    return None  # USDT<->DAI direct swap: no tracked historical pair


def curve_volume_usd(sold_symbol: str, sold_amount: float, bought_symbol: str,
                      bought_amount: float, prices: PriceCache) -> float:
    """Average of both legs' USD value (each leg's token amount x that
    token's live USD price) — uses a real live price, not a naive $1
    assumption, so this stays meaningful during an active depeg."""
    sold_usd = sold_amount * prices.get(sold_symbol)
    bought_usd = bought_amount * prices.get(bought_symbol)
    return (sold_usd + bought_usd) / 2.0


def _decode_uniswap_gap_log(http_url: str, log: dict, pool_name: str, pair: str, meta: dict, prices: PriceCache) -> dict | None:
    topic0 = log["topics"][0]
    block_number = int(log["blockNumber"], 16)
    base = {
        "received_at": now_iso(), "event_ts": eth_block_timestamp(http_url, block_number),
        "block_number": block_number,
        "tx_hash": log["transactionHash"], "log_index": int(log["logIndex"], 16),
        "pool_address": log["address"], "pool_name": pool_name,
        "blockchain": "ethereum", "source": "alchemy_getlogs_replay",
        "project": "uniswap_v2", "pair": pair,
    }
    if topic0.lower() == TOPIC_SYNC.lower():
        return {**base, "event_type": "SYNC", **decode_uniswap_sync(log, meta)}
    if topic0.lower() == TOPIC_SWAP_V2.lower():
        decoded = decode_uniswap_swap(log, meta)
        other_symbol = "USDT" if pair == "USDC_USDT" else "DAI"
        vol_usd = (decoded["amount0_in"] + decoded["amount0_out"]) / 2.0 * prices.get("USDC") + (
            decoded["amount1_in"] + decoded["amount1_out"]) / 2.0 * prices.get(other_symbol)
        return {**base, "event_type": "SWAP", "volume_usd": vol_usd, **decoded}
    return None


async def fetch_replay_gap(http_url: str, from_block: int, to_block: int,
                            uni_usdt_meta: dict, uni_dai_meta: dict, prices: PriceCache) -> list[dict]:
    """Gap-fill via eth_getLogs for the block range missed while
    disconnected — a WebSocket subscription does not replay missed events,
    but block-range log queries work retroactively. Records from here are
    tagged source='alchemy_getlogs_replay', distinct from 'alchemy_live'
    (genuine real-time push events)."""
    if from_block > to_block:
        return []
    print(f"[gap-fill] querying eth_getLogs for blocks {from_block}..{to_block}")
    records = []

    curve_logs = eth_get_logs(http_url, CURVE_3POOL_ADDRESS, [TOPIC_TOKEN_EXCHANGE], from_block, to_block)
    for log in curve_logs:
        try:
            decoded = decode_curve_token_exchange(log)
            pair = curve_pair_for(decoded["sold_symbol"], decoded["bought_symbol"])
            vol_usd = curve_volume_usd(decoded["sold_symbol"], decoded["sold_amount"],
                                        decoded["bought_symbol"], decoded["bought_amount"], prices)
            block_number = int(log["blockNumber"], 16)
            records.append({
                "received_at": now_iso(), "event_ts": eth_block_timestamp(http_url, block_number),
                "block_number": block_number,
                "tx_hash": log["transactionHash"], "log_index": int(log["logIndex"], 16),
                "pool_address": log["address"], "pool_name": "curve_3pool",
                "blockchain": "ethereum", "source": "alchemy_getlogs_replay",
                "project": "curve", "event_type": "SWAP", "pair": pair, "volume_usd": vol_usd,
                **decoded,
            })
        except Exception as e:
            print(f"[gap-fill] curve decode error: {e!r}")

    uni_usdt_logs = eth_get_logs(http_url, UNISWAP_V2_USDC_USDT_ADDRESS,
                                  [[TOPIC_SYNC, TOPIC_SWAP_V2]], from_block, to_block)
    for log in uni_usdt_logs:
        try:
            rec = _decode_uniswap_gap_log(http_url, log, "uniswap_v2_usdc_usdt", "USDC_USDT", uni_usdt_meta, prices)
            if rec:
                records.append(rec)
        except Exception as e:
            print(f"[gap-fill] uniswap USDC_USDT decode error: {e!r}")

    uni_dai_logs = eth_get_logs(http_url, UNISWAP_V2_USDC_DAI_ADDRESS,
                                 [[TOPIC_SYNC, TOPIC_SWAP_V2]], from_block, to_block)
    for log in uni_dai_logs:
        try:
            rec = _decode_uniswap_gap_log(http_url, log, "uniswap_v2_usdc_dai", "USDC_DAI", uni_dai_meta, prices)
            if rec:
                records.append(rec)
        except Exception as e:
            print(f"[gap-fill] uniswap USDC_DAI decode error: {e!r}")

    print(f"[gap-fill] decoded {len(records)} records from {len(curve_logs)} curve, "
          f"{len(uni_usdt_logs)} uni-usdt, {len(uni_dai_logs)} uni-dai logs")
    return records


async def run(api_key: str, writer: RolloverWriter, state: StreamState, prices: PriceCache):
    ws_url = f"wss://eth-mainnet.g.alchemy.com/v2/{api_key}"
    http_url = f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"

    print("Fetching Uniswap V2 pool metadata (token0/token1, decimals)...")
    uni_usdt_meta = fetch_uniswap_v2_pool_metadata(http_url, UNISWAP_V2_USDC_USDT_ADDRESS)
    uni_dai_meta = fetch_uniswap_v2_pool_metadata(http_url, UNISWAP_V2_USDC_DAI_ADDRESS)
    print(f"  USDC_USDT: token0={uni_usdt_meta['token0']} token1={uni_usdt_meta['token1']}")
    print(f"  USDC_DAI:  token0={uni_dai_meta['token0']} token1={uni_dai_meta['token1']}")
    pool_meta = {
        "uniswap_v2_usdc_usdt": uni_usdt_meta,
        "uniswap_v2_usdc_dai": uni_dai_meta,
    }

    # Gap-fill: if we have a prior state (not first-ever run) and the chain
    # has moved on since, backfill the missed block range before resuming
    # the live subscription.
    current_head = eth_block_number(http_url)
    if state.last_block > 0 and current_head > state.last_block:
        gap_records = await fetch_replay_gap(http_url, state.last_block + 1, current_head, uni_usdt_meta, uni_dai_meta, prices)
        for rec in gap_records:
            writer.write(rec)
        writer.flush()
        state.update(current_head)

    backoff_idx = 0
    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                subs = [
                    {"id": 1, "method": "eth_subscribe", "params": ["logs", {
                        "address": CURVE_3POOL_ADDRESS, "topics": [TOPIC_TOKEN_EXCHANGE]}]},
                    {"id": 2, "method": "eth_subscribe", "params": ["logs", {
                        "address": UNISWAP_V2_USDC_USDT_ADDRESS, "topics": [[TOPIC_SYNC, TOPIC_SWAP_V2]]}]},
                    {"id": 3, "method": "eth_subscribe", "params": ["logs", {
                        "address": UNISWAP_V2_USDC_DAI_ADDRESS, "topics": [[TOPIC_SYNC, TOPIC_SWAP_V2]]}]},
                ]
                sub_id_to_pool = {}
                names = {1: "curve_3pool", 2: "uniswap_v2_usdc_usdt", 3: "uniswap_v2_usdc_dai"}
                for req in subs:
                    await ws.send(json.dumps(req))
                    resp = json.loads(await ws.recv())
                    sub_id_to_pool[resp["result"]] = names[req["id"]]
                    print(f"Subscribed: {names[req['id']]} -> {resp['result']}")

                backoff_idx = 0  # reset backoff after a successful connect
                print("\nListening indefinitely (Ctrl+C to stop)...\n")

                while True:
                    raw_msg = await ws.recv()
                    msg = json.loads(raw_msg)
                    if msg.get("method") != "eth_subscription":
                        continue
                    sub_id = msg["params"]["subscription"]
                    pool_name = sub_id_to_pool.get(sub_id, "unknown")
                    log = msg["params"]["result"]
                    topic0 = log["topics"][0]
                    block_number = int(log["blockNumber"], 16)

                    base_record = {
                        "received_at": now_iso(),
                        # Fetched for every live event too (not just gap-fill),
                        # for consistent semantics: event_ts is always the
                        # authoritative on-chain time used for hourly
                        # bucketing, received_at is always "when this process
                        # observed it" (an audit field). One extra eth_call
                        # per event is negligible at this event rate.
                        "event_ts": eth_block_timestamp(http_url, block_number),
                        "block_number": block_number,
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
                            pair = curve_pair_for(decoded["sold_symbol"], decoded["bought_symbol"])
                            vol_usd = curve_volume_usd(
                                decoded["sold_symbol"], decoded["sold_amount"],
                                decoded["bought_symbol"], decoded["bought_amount"], prices
                            )
                            record = {**base_record, "project": "curve", "event_type": "SWAP",
                                      "pair": pair, "volume_usd": vol_usd, **decoded}
                            writer.write(record)

                            balances = fetch_curve_balances(http_url, CURVE_3POOL_ADDRESS)
                            dai_bal = balances[0] / (10 ** CURVE_3POOL_TOKENS[0]["decimals"])
                            usdc_bal = balances[1] / (10 ** CURVE_3POOL_TOKENS[1]["decimals"])
                            usdt_bal = balances[2] / (10 ** CURVE_3POOL_TOKENS[2]["decimals"])
                            price, is_valid, anomaly, raw_note = safe_ratio(usdc_bal, usdt_bal)
                            snapshot_record = {
                                **base_record, "project": "curve", "event_type": "RESERVE_SNAPSHOT",
                                "pair": "USDC_USDT",
                                "dai_balance": dai_bal, "usdc_balance": usdc_bal, "usdt_balance": usdt_bal,
                                "implied_price": price, "is_valid_price": is_valid,
                                "anomaly_flag": anomaly,
                                "raw_price_value": raw_note if raw_note else str(price),
                            }
                            writer.write(snapshot_record)

                        elif pool_name in ("uniswap_v2_usdc_usdt", "uniswap_v2_usdc_dai"):
                            meta = pool_meta[pool_name]
                            pair = "USDC_USDT" if pool_name == "uniswap_v2_usdc_usdt" else "USDC_DAI"
                            if topic0.lower() == TOPIC_SYNC.lower():
                                decoded = decode_uniswap_sync(log, meta)
                                writer.write({**base_record, "project": "uniswap_v2",
                                              "event_type": "SYNC", "pair": pair, **decoded})
                            elif topic0.lower() == TOPIC_SWAP_V2.lower():
                                decoded = decode_uniswap_swap(log, meta)
                                other_symbol = "USDT" if pair == "USDC_USDT" else "DAI"
                                vol_usd = (
                                    decoded["amount0_in"] + decoded["amount0_out"]
                                ) / 2.0 * prices.get("USDC") + (
                                    decoded["amount1_in"] + decoded["amount1_out"]
                                ) / 2.0 * prices.get(other_symbol)
                                writer.write({**base_record, "project": "uniswap_v2",
                                              "event_type": "SWAP", "pair": pair,
                                              "volume_usd": vol_usd, **decoded})

                        state.update(block_number)

                    except Exception as e:
                        print(f"[decode error] {pool_name}: {e!r} (tx={log.get('transactionHash')})")

        except (websockets.exceptions.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
            writer.flush()
            delay = RECONNECT_BACKOFF_SECS[min(backoff_idx, len(RECONNECT_BACKOFF_SECS) - 1)]
            backoff_idx += 1
            print(f"[reconnect] connection lost ({e!r}), retrying in {delay}s...")
            await asyncio.sleep(delay)

            # On reconnect, fill whatever gap opened up while disconnected.
            current_head = eth_block_number(http_url)
            if current_head > state.last_block:
                gap_records = await fetch_replay_gap(http_url, state.last_block + 1, current_head, uni_usdt_meta, uni_dai_meta, prices)
                for rec in gap_records:
                    writer.write(rec)
                writer.flush()
                state.update(current_head)


def main():
    api_key = load_api_key()
    writer = RolloverWriter(OUTPUT_DIR)
    state = StreamState(STATE_FILE)
    prices = PriceCache()
    try:
        asyncio.run(run(api_key, writer, state, prices))
    finally:
        writer.flush()
        print(f"\nWrote {writer.count} records total to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
