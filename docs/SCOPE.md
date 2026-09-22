# Scope

## Locked Decisions

- **Project name:** Meridian
- **Domain:** Stablecoin depeg / liquidity stress early warning
- **Explicitly OUT of scope for now:** HBase, Zookeeper, GenAI/generative
  components
- **Historical depeg case studies for validation:**
  - TerraUSD (May 2022)
  - USDC (March 2023, SVB-related)
- **On-chain data source: RESOLVED — dual-source split by time horizon**
  - **Dune Analytics** for historical backfill (one-time, complete for the
    initial validation window; March 2023 USDC depeg confirmed visible in
    the data)
  - **Alchemy WebSocket** (direct RPC) for the live streaming feed (ongoing)
  - See [ARCHITECTURE.md](ARCHITECTURE.md) and [DATA_SOURCES.md](DATA_SOURCES.md)
    for the full detail — BigQuery was considered and dropped as redundant
    with Dune for the historical need

## Pending Decisions

> These are open and should **not** be assumed. Resolve explicitly before
> depending on them elsewhere.

- **Which stablecoins to cover:** candidates are USDT, USDC, DAI, FRAX
- **Which chain(s):** Ethereum mainnet only, or multi-chain
- **Time range for historical data**
- **Lab 2 (word count) mapping** — see [LAB_MAPPING.md](LAB_MAPPING.md)
