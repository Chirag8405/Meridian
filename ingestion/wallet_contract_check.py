"""
Data-quality check for the wallet PageRank results: a top-ranked "wallet"
that's actually a contract (router, aggregator, MEV bot) is infrastructure
everyone routes through, not an influential trader in a meaningful sense —
this needs to be verifiable, not guessed from address patterns.

Checks eth_getCode via Alchemy for every WALLET node that appears in the
top 15 overall and/or top 10 of any window's ranking, writes results to
meridian.wallet_labels. is_contract=TRUE means real bytecode exists at
that address (a definitive, verifiable fact — not an inference).
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

# Known router/aggregator addresses seen commonly in DEX trade data — used
# only to offer a label when eth_getCode confirms a contract; the
# is_contract determination itself never depends on this list.
KNOWN_CONTRACTS = {
    "0x1111111254fb6c44bac0bed2854e76f90643097d": "1inch v4 Router",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch v5 Router",
    "0x11111112542d85b3ef69ae05771c2dccff4faa26": "1inch v3 Router",
    "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x Exchange Proxy",
    "0x881d40237659c251811cec9c364ef91dc08d300": "Metamask Swap Router",
    "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "Uniswap Universal Router",
    "0xe592427a0aece92de3edee1f18e0157c05861564": "Uniswap V3 Router",
    "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "Uniswap V2 Router",
    "0x9008d19f58aabd9ed0d60971565aa8510560ab41": "CoW Protocol Settlement",
    "0x00000000009726632680fb29d3f7a9734e3010e2": "1inch Fusion Settlement",
}


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


def get_code(http_url: str, address: str) -> str:
    resp = requests.post(http_url, json={
        "jsonrpc": "2.0", "id": 1, "method": "eth_getCode",
        "params": [address, "latest"],
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["result"]


def check_addresses(addresses: list) -> list:
    api_key = load_api_key()
    http_url = f"https://eth-mainnet.g.alchemy.com/v2/{api_key}"
    results = []
    for addr in addresses:
        addr_lc = addr.lower()
        code = get_code(http_url, addr_lc)
        is_contract = code is not None and code != "0x"
        label = KNOWN_CONTRACTS.get(addr_lc) if is_contract else None
        results.append({
            "address": addr_lc,
            "is_contract": is_contract,
            "label": label,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        })
        tag = f" ({label})" if label else ""
        print(f"  {addr_lc}: {'CONTRACT' if is_contract else 'EOA'}{tag}")
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: wallet_contract_check.py <address1> [address2 ...]")
    addrs = sys.argv[1:]
    print(f"Checking {len(addrs)} addresses via eth_getCode...")
    results = check_addresses(addrs)
    out_file = PROJECT_ROOT / "data" / "processed" / "wallet_labels.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {len(results)} results to {out_file}")
    n_contracts = sum(1 for r in results if r["is_contract"])
    print(f"{n_contracts}/{len(results)} are contracts")
