# Scope

## Locked Decisions

- **Project name:** Meridian
- **Domain:** Stablecoin depeg / liquidity stress early warning
- **Explicitly OUT of scope for now:** HBase, Zookeeper
- **GenAI: IN scope** (decided later): a Groq-backed grounded assistant, risk advisories and an
  offline evaluation. See [GENAI_ASSISTANT_PLAN.md](GENAI_ASSISTANT_PLAN.md). The rule-based pipeline,
  not the model, produces the risk assessment.
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

## Decisions resolved in practice

> These were open early in the project and are now settled by what was built.

- **Stablecoins covered:** USDC, USDT, DAI and TerraUSD (UST), as pairs on Curve and Uniswap V2
  (USDC_DAI, USDC_USDT, UST_DAI, UST_USDC, UST_USDT). FRAX was a candidate and is not covered.
  Live tracking covers the USDC pairs only (UST has no live pool activity).
- **Chain:** Ethereum mainnet only.
- **Historical time range:** USDC_USDT/curve from Dec 2022 to May 2023; UST_USDC/curve from
  Apr to Jun 2022 (the available data starts after UST was already destabilised; see FINDINGS.md).
- **Lab 2 (word count) mapping:** not required; closed. See [LAB_MAPPING.md](LAB_MAPPING.md).
