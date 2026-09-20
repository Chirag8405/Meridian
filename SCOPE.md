# Scope

## Locked Decisions

- **Project name:** Meridian
- **Domain:** Stablecoin depeg / liquidity stress early warning
- **Explicitly OUT of scope for now:** HBase, Zookeeper, GenAI/generative
  components
- **Historical depeg case studies for validation:**
  - TerraUSD (May 2022)
  - USDC (March 2023, SVB-related)

## Pending Decisions

> These are open and should **not** be assumed. Resolve explicitly before
> depending on them elsewhere.

- **Which on-chain data source:** BigQuery public Ethereum dataset vs. Dune
  Analytics vs. direct RPC (Infura/Alchemy) — see [DATA_SOURCES.md](DATA_SOURCES.md)
- **Which stablecoins to cover:** candidates are USDT, USDC, DAI, FRAX
- **Which chain(s):** Ethereum mainnet only, or multi-chain
- **Time range for historical data**
- **Lab 2 (word count) mapping** — see [LAB_MAPPING.md](LAB_MAPPING.md)
