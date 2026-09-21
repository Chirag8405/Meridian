# Architecture

Meridian is organized into five layers, from raw data ingestion through to
the user-facing dashboard.

## 1. Data Sources Layer

- On-chain transaction / pool-state data — split into two sources by
  time horizon (see [DATA_SOURCES.md](DATA_SOURCES.md)):
  - **Dune Analytics** for historical backfill (one-time, already run for
    an initial validation window — see below)
  - **Alchemy WebSocket** (direct RPC) for the live streaming feed (ongoing)
- Stablecoin price feeds
- Historical depeg incident records (curated)
- Exchange price data

## 2. Data Integration Layer

- **Historical backfill (Dune):** `ingestion/dune_test_pull.py` executes
  ad-hoc SQL against Dune's `dex.trades` table via their SQL execution API,
  aggregating pool trades into hourly buckets. Validated against the March
  2023 USDC depeg (Curve 3pool) — the implied price series clearly captured
  the drop to ~$0.88. This is a one-time/periodic backfill, not a running
  process.
- **Live streaming (Alchemy):** `ingestion/alchemy_live_feed.py` subscribes
  to on-chain events over a WebSocket (`eth_subscribe` with a `logs` filter)
  for the same pools the historical backfill covers, decoding each event as
  it arrives. This is an ongoing process, intended to feed the Spark
  Structured Streaming component (not yet built — see
  [ROADMAP.md](ROADMAP.md)).
  - Curve pools and Uniswap V2 pools have genuinely different event models:
    Uniswap V2 emits both `Sync` (reserve state) and `Swap` (trade) events;
    Curve only emits `TokenExchange` (trade) — there's no native
    reserve-update event on Curve, so the live feed script synthesizes an
    equivalent `RESERVE_SNAPSHOT` record via an `eth_call` to the pool's
    `balances()` function after each trade, rather than pretending Curve has
    a `Sync` event it doesn't.
- Sqoop for transferring curated historical incident records from a staging
  relational DB

## 3. Storage Layer

- **HDFS** for raw ingested data
- **Hive** for the structured/partitioned query layer
- **MongoDB** for flexible semi-structured documents (pool-state JSON,
  price API responses)

## 4. Analytics & Management Layer

- **Spark** for baseline (calm-market) and crisis-window liquidity/price-
  deviation statistics (`spark/baseline_crisis_stats.scala`, results in
  `meridian.baseline_stats` / `meridian.crisis_stats`) — chosen over
  MapReduce for this computation once it stopped being lab-constrained,
  since percentiles and stddev are native Spark SQL aggregates rather than
  hand-rolled MapReduce logic. A separate MapReduce job may still be built
  to satisfy Lab 3's specific requirement (see
  [LAB_MAPPING.md](LAB_MAPPING.md)) — that's a lab-coverage need distinct
  from this actual statistics computation, which is now Spark's job.
  **Not every pair gets scored against its own baseline** — see
  [FINDINGS.md](FINDINGS.md) for why UST has no reliable baseline in this
  dataset, and the two-path design that implies for the risk model below.
- **Spark** for PageRank-based wallet/pool influence ranking
- **CURE/Canopy clustering** of historical depeg events by stress signature
- **Spark Structured Streaming** for live pool-ratio/price monitoring
- **MLlib** for depeg-risk scoring — routes pairs through one of two
  scoring paths based on `baseline_stats.baseline_status`
  ([FINDINGS.md](FINDINGS.md)): deviation-from-own-baseline when a
  reliable baseline exists, absolute-deviation-from-$1.00 plus
  trend/velocity when it doesn't

## 5. Application Layer

- Dashboard displaying live risk scores per stablecoin

## Workflow Diagram (Description)

```
Dune (historical, one-time)  ─┐
                               ├─→  HDFS  →  Hive / MongoDB  →  Spark / MapReduce  →  Dashboard
Alchemy WS (live, ongoing)   ─┘
```

Raw on-chain and market data lands in HDFS (and MongoDB for semi-structured
documents), gets structured and partitioned in Hive, is processed by Spark
and MapReduce jobs for statistics, clustering, ranking, and risk scoring, and
the results surface on a live dashboard. Historical (Dune) and live
(Alchemy) records share the same eventual Hive schema
(`meridian.stablecoin_pool_hourly` — see [hive/schema.sql](hive/schema.sql)),
distinguished by the `source` column (`dune` vs `alchemy_live`), so
downstream analytics don't need to know which pipeline a row came from.
