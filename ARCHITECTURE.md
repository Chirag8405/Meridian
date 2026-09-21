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
- **Spark (GraphX)** for PageRank-based wallet/pool influence ranking
  (`spark/wallet_pagerank.scala`, results in `meridian.wallet_pagerank` /
  `meridian.wallet_labels`). Requires wallet-level trade data
  (`taker`/`tx_from`/`tx_to` per individual trade), which the hourly-
  aggregated backfill doesn't have — a separate raw pull
  (`ingestion/dune_wallet_pull.py` → `meridian.wallet_trades_raw`, ~135K
  rows across the 4 tracked pools) feeds this specifically.
  - **Bipartite construction**: nodes = wallets + pools, edges = trade
    volume between a wallet and a pool, **bidirectional** (wallet→pool and
    pool→wallet, both weighted by the same volume). A one-directional
    wallet→pool graph is structurally degenerate for PageRank — pools
    would accumulate all rank as pure sinks and never redistribute it
    back, so wallets would only ever get the uniform teleportation score.
    Bidirectional edges let rank flow both ways, the standard technique
    for bipartite/recommender-graph PageRank.
  - **Weighted PageRank is a custom implementation**: GraphX's built-in
    `Graph.pageRank()` does not support edge weights — it normalizes
    purely by out-degree. Since higher-volume wallet-pool relationships
    are meant to carry more influence, this uses a hand-rolled
    Pregel-based weighted PageRank (edge weights normalized to transition
    probabilities per source vertex), not the convenience method.
  - **A large fraction of top-ranked "wallets" are contracts, not
    traders**: verified via `eth_getCode` (`meridian.wallet_labels`), not
    inferred from address patterns — 29 of the top 35 ranked wallets
    across all computed windows are contracts (routers, aggregators, or
    other DeFi infrastructure), not EOAs. This is load-bearing for how
    results should be read: high PageRank for a contract address means
    "lots of trades route through this," not "this is an influential
    trader." See [FINDINGS.md](FINDINGS.md) for the full breakdown and the
    calm-vs-crisis wallet-concentration analysis.
- **K-Means clustering (MLlib)** of hourly stress signatures
  (`spark/stress_clustering.scala`, results in `meridian.stress_clusters` /
  `meridian.stress_cluster_profiles`). CURE/Canopy have no native MLlib
  support and weren't worth hand-rolling once lab-mapping stopped being a
  project goal, so this uses standardized K-Means instead.
  - **Unit of clustering is (pair, project, hour)**, not the 2 crisis
    events themselves — too small an n to cluster meaningfully. Features:
    price/volume/trade_count deviation plus an anomaly-flag indicator.
  - **Two-path feature design, extended beyond the original price-only
    proposal**: RELIABLE pairs get z-scores against their own
    `baseline_stats` (calm-window) mean/stddev. `NO_RELIABLE_BASELINE`
    (UST) pairs get peg-deviation for price (no calm baseline to score
    against) — and, since `baseline_stats`' own volume/trade_count numbers
    for UST are contaminated by the same pre/post-collapse blended window
    as its price numbers, volume/trade_count use a fresh self-referential
    full-history mean/stddev instead of `baseline_stats`. No UST rows are
    silently dropped; only the 4 genuinely-undefined `NAN_PRICE` rows are
    excluded (RELIABLE pairs only).
  - **k=4, chosen empirically** via elbow (WSSSE) + silhouette sweep over
    k=2..10, sanity-checked against the known USDC Mar 2023 and UST May
    2022 crisis windows — see [FINDINGS.md](FINDINGS.md) for the full
    sweep, the sanity-check results, and why the high silhouette scores
    across nearly all k don't by themselves indicate a well-tuned k.
- **Spark Structured Streaming** for live pool-ratio/price monitoring
- **Rule-based baseline risk score** (`spark/risk_scores_baseline.scala`,
  results in `meridian.risk_scores_baseline`) — built deliberately *before*
  any ML model training, so a trained model has a concrete, explainable
  score to validate against rather than nothing. Composite `risk_score`
  (0-100) combines four independently-normalized `[0,1]` components:
  price deviation severity and volume/trade_count deviation severity
  (reused from `meridian.stress_clusters`, weight 0.40/0.25), cluster
  membership severity (a lookup table grounded in each cluster's actual
  raw profile, weight 0.15 — deliberately low since cluster membership is
  *derived from* the other features and a higher weight would double-count
  the same signal), and top-10-wallet PageRank concentration for the row's
  window (weight 0.20, zeroed for UST rows — see
  [FINDINGS.md](FINDINGS.md) for why that signal is validated for USDC but
  inverted/unreliable for UST). Validated against the known USDC Mar 2023
  and UST May 2022 crisis windows: calm hours score tightly around a
  median of 4.36, every crisis-labeled category scores substantially
  higher (medians 12-39) — see FINDINGS.md for the full distribution and
  two notable nuances the validation surfaced.
- **MLlib crisis classifier** (`spark/crisis_features.scala` +
  `spark/crisis_classifier.scala`, results in `meridian.crisis_features` /
  `meridian.crisis_classifier_predictions` / `meridian.crisis_classifier_metrics`)
  — trained specifically to fix the rule-based baseline's documented
  blind spot (magnitude-only, no trend/trajectory). Binary CALM/CRISIS
  labels grounded in independently-known historical crisis dates (not
  derived from our own severity metrics, to keep the model-vs-baseline
  comparison meaningful). Validated via leave-one-coin-out: train on
  USDC, test on UST (and vice versa, necessarily coin-blended for the
  CALM class since UST has no calm rows at all in this dataset). Result:
  a model trained only on USDC's milder depeg genuinely **beats** the
  baseline generalizing to UST's structurally different collapse (F1 0.915
  vs. 0.858), but loses decisively in the harder reverse direction (severe
  UST pattern → mild USDC pattern, F1 0.611 vs. 0.995). A first training
  run surfaced a leakage-adjacent feature (`wallet_concentration_severity`,
  a window-constant near-proxy for the label) that had to be found and
  removed before these results could be trusted — see
  [FINDINGS.md](FINDINGS.md) for the full writeup, including a more
  precise-than-expected finding on whether the trend/velocity features
  actually earned their place.

## 5. Application Layer

- **Next.js findings dashboard** (`dashboard/`, see
  [README](dashboard/README.md)) — a technical-reviewer-facing page
  presenting the project's real, already-computed results: current
  `risk_score` per pair, the USDC/UST crisis timelines on a shared price
  axis, the ML classifier's honest win/loss comparison against the
  baseline, and the wallet PageRank contract-vs-EOA finding. **Not a live
  tool** — it reads static JSON (`dashboard/data/*.json`) materialized by
  `spark/export_dashboard_data.scala`, not Hive directly. Confirmed via
  measurement (46-56s for a trivial single-table `COUNT(*)`, even on a
  warmed-up cluster) that live Hive queries are unsuitable for a
  request-driven page — Hive runs on the MapReduce execution engine here
  (see Known Integration Fixes in [CLAUDE.md](CLAUDE.md)), and its
  per-query container/JVM startup cost dominates regardless of data
  volume. The export is rerun manually after any pipeline update, same
  operating model as every other batch job in this project — there is no
  streaming consumer yet, so the dashboard states its own data vintage
  prominently rather than posing as live.

## Workflow Diagram (Description)

```
Dune (historical, one-time)  ─┐
                               ├─→  HDFS  →  Hive / MongoDB  →  Spark / MapReduce  →  JSON export  →  Dashboard
Alchemy WS (live, ongoing)   ─┘
```

Raw on-chain and market data lands in HDFS (and MongoDB for semi-structured
documents), gets structured and partitioned in Hive, is processed by Spark
and MapReduce jobs for statistics, clustering, ranking, and risk scoring.
Historical (Dune) and live (Alchemy) records share the same eventual Hive
schema (`meridian.stablecoin_pool_hourly` — see
[hive/schema.sql](hive/schema.sql)), distinguished by the `source` column
(`dune` vs `alchemy_live`), so downstream analytics don't need to know
which pipeline a row came from. The dashboard does not query any of this
live — a batch export step materializes the small, pre-known slice of
results it needs into static JSON, which is what the page actually reads.
