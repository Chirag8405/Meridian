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
  to on-chain events over a WebSocket (`eth_subscribe` with a `logs`
  filter) across 4 pools — Curve 3pool (covers USDC_USDT + USDC_DAI) +
  Uniswap V2 USDC_USDT + Uniswap V2 USDC_DAI, full parity with the
  historical backfill's coverage (UST is dead — no live pool activity to
  track). Runs indefinitely under a systemd `--user` service
  (`systemd/meridian-live-feed.service`), not a one-shot process. Feeds
  `spark/stream_alchemy_live.scala` (see the Analytics layer below) via
  small, atomically-renamed JSON files in a landing directory — not a
  direct connection, since Spark Structured Streaming has no native
  WebSocket source (confirmed against Spark's docs before designing this;
  only File, Kafka, and testing-only Socket/Rate sources exist, and Kafka
  is new infrastructure this project has deliberately avoided, same
  precedent as the "no HBase/Zookeeper" descoping).
  - Curve pools and Uniswap V2 pools have genuinely different event models:
    Uniswap V2 emits both `Sync` (reserve state) and `Swap` (trade) events;
    Curve only emits `TokenExchange` (trade) — there's no native
    reserve-update event on Curve, so the live feed script synthesizes an
    equivalent `RESERVE_SNAPSHOT` record via an `eth_call` to the pool's
    `balances()` function after each trade, rather than pretending Curve has
    a `Sync` event it doesn't.
  - **Resilience**: a WebSocket subscription does not replay missed
    events — a machine sleep/disconnect of hours+ loses events from the
    push stream entirely. On reconnect (in-process, with backoff) or
    process restart, the gap is filled via `eth_getLogs` for the missed
    block range, tagged `source='alchemy_getlogs_replay'` (vs
    `'alchemy_live'` for genuine real-time push events) so the two stay
    distinguishable downstream. Alchemy's free tier caps `eth_getLogs` at
    a 10-block range per call (confirmed empirically, not documented
    upfront) — chunked automatically, since the whole point of gap-fill is
    recovering from potentially thousands of missed blocks.
  - **USD volume**: historical `volume_usd` came from Dune's own real
    market-price valuation; live on-chain events only give token-to-token
    ratios. Fetches a live USD reference price per stablecoin from
    CoinGecko's keyless public API (confirmed no API key needed at this
    call volume) rather than assuming 1 stablecoin == $1, which would be
    wrong exactly during an active depeg.
  - **Event timestamps**: every record carries `event_ts` (the real
    on-chain block timestamp, via `eth_getBlockByNumber`), not just
    `received_at` (when this process happened to observe it) — required
    for correctness, since a gap-filled event recovered hours or days late
    would otherwise get bucketed into the wrong hour if windowed on
    `received_at`.
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
- **Spark Structured Streaming** live consumer
  (`spark/stream_alchemy_live.scala`) — watches the landing directory
  `ingestion/alchemy_live_feed.py` writes to (File source; no native
  WebSocket source exists in Structured Streaming), aggregates to the same
  hourly grain as the batch pipeline (10-minute trigger — a freshness
  choice, not a resource-conservation one, since a streaming query's
  micro-batches are cheap ticks within one long-running application, not
  fresh job launches like Hive-on-MapReduce elsewhere in this project),
  and appends into the SAME Hive tables the batch pipeline uses
  (`meridian.stablecoin_pool_hourly`, `meridian.risk_scores_baseline`).
  Same storage as the historical data, but the dashboard presents this as
  a separate "current" view rather than splicing 2026 live readings onto
  the March 2023/May 2022 crisis-timeline charts — a ~3+ year gap spliced
  into one chart would be misleading regardless of how it's labeled, and
  `baseline_stats` itself was computed from Dec 2022-May 2023 data, so
  scoring current readings against it without re-validation is a separate,
  flagged (not yet resolved) methodological question.
  - **Cluster assignment never re-fits K-Means.** Live rows are scored via
    `.transform()` against the frozen `StandardScalerModel`/`KMeansModel`
    persisted by `spark/persist_clustering_model.scala` (verified
    byte-identical to the published `meridian.stress_clusters` assignments
    before being saved — 15,603 rows compared, 0 mismatches). See
    FINDINGS.md's "Guarantee" section — re-fitting on historical+live
    combined would risk silently shifting the already-published historical
    cluster numbers this document reports elsewhere.
  - **Watermark (2h) + append output mode**, not update mode: emits each
    hourly window's aggregate exactly once, only after the watermark has
    passed it, avoiding multiple partial-row inserts for the same hour
    that a plain (non-ACID) Hive table can't de-duplicate.
  - Runs indefinitely under a systemd `--user` service
    (`systemd/meridian-stream-consumer.service`), same rationale as the
    live feed ingester above — `nohup` (this project's convention for
    single long batch jobs) has no auto-restart on crash or reboot, which
    matters for something meant to run indefinitely, not just once.
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
  [README](../dashboard/README.md)) — a technical-reviewer-facing page
  presenting the project's real, already-computed results: current
  `risk_score` per pair (including the live Alchemy feed's
  `current_risk_live`, updated by the streaming consumer — see the Live
  streaming subsection in [SETUP.md](SETUP.md)), the USDC/UST crisis
  timelines on a shared price axis, the ML classifier's honest win/loss
  comparison against the baseline, and the wallet PageRank
  contract-vs-EOA finding. It never queries Hive directly, live or
  otherwise — confirmed via measurement (46-56s for a trivial
  single-table `COUNT(*)`, even on a warmed-up cluster) that live Hive
  queries are unsuitable for a request-driven page, since Hive runs on
  the MapReduce execution engine here (see Known Integration Fixes in
  [CLAUDE.md](../CLAUDE.md)) and its per-query container/JVM startup cost
  dominates regardless of data volume.

  **Deployed data flow (Supabase + Render), replacing the earlier
  static-JSON-at-build-time approach:** `spark/export_dashboard_data.scala`
  still materializes the same fixed queries into JSON under
  `dashboard/data/*.json` (rerun manually after any pipeline update, same
  operating model as every other batch job in this project) — but that
  JSON is now an intermediate artifact, not what the deployed page reads.
  `ingestion/push_to_supabase.py` pushes it to a free-tier Supabase
  Postgres project (`supabase/schema.sql`; public read-only via Row Level
  Security, writes via a secret key that bypasses RLS, run locally only —
  see `.env.example`). A small FastAPI service (`backend/main.py`),
  deployed on Render's free tier, reads Supabase with a read-only
  publishable key and exposes `GET /api/dashboard-data` (all 7 tables,
  one combined response) and `GET /health` (a genuine Supabase query, not
  a stub). The Vercel-deployed dashboard's Next.js Server Components
  fetch that endpoint server-to-server with a 60-second revalidate window
  (`dashboard/lib/data.ts`) — this was chosen specifically over a
  client-side fetch or a Vercel API-route proxy because server-to-server
  calls aren't subject to browser CORS, so no CORS configuration is
  needed anywhere in this chain. New data therefore reaches the deployed
  dashboard within 60 seconds of a `push_to_supabase.py` run, with no git
  push or rebuild required — except that **Render must already be live
  and correctly configured with valid Supabase credentials before a
  Vercel build runs**, since `revalidate` fetches are also used for
  build-time static generation; a build triggered before that will fail
  cleanly rather than deploy something broken (confirmed by testing
  locally with `RENDER_API_URL` unset). Full provisioning steps in
  SETUP.md's "Live backend (Supabase + Render)" section.

  Two free-tier constraints worth flagging explicitly, not burying:
  Supabase's free project pauses after 7 days with no traffic (recoverable
  from its dashboard, but an avoidable interruption) and Render's free web
  service spins down after 15 minutes idle, adding a cold-start delay to
  the next request. Both are addressed with a single UptimeRobot monitor
  (free tier, 5-minute interval) pinging Render's `/health`, which in turn
  genuinely queries Supabase on every ping — real traffic to both, not a
  keepalive stub. The real cost: Render's free tier grants 750 instance-
  hours/month, and staying awake 24/7 this way consumes roughly 720-744 of
  those hours — effectively the entire monthly allowance. That's fine for
  a single Render service with no other usage on the account, but would
  become a real constraint if this account hosts anything else on Render.

  No fallback to static JSON is implemented if Render is unreachable at
  request time — a deliberate, confirmed scope decision to ship the pure
  replacement first rather than add fallback complexity speculatively.

## Workflow Diagram (Description)

```
Dune (historical, one-time)  ─┐
                               ├─→  HDFS  →  Hive / MongoDB  →  Spark / MapReduce  →  JSON export  →  Supabase  →  Render API  →  Dashboard
Alchemy WS (live, ongoing)   ─┘
```

Raw on-chain and market data lands in HDFS (and MongoDB for semi-structured
documents), gets structured and partitioned in Hive, is processed by Spark
and MapReduce jobs for statistics, clustering, ranking, and risk scoring.
Historical (Dune) and live (Alchemy) records share the same eventual Hive
schema (`meridian.stablecoin_pool_hourly` — see
[hive/schema.sql](../hive/schema.sql)), distinguished by the `source` column
(`dune` vs `alchemy_live`), so downstream analytics don't need to know
which pipeline a row came from. The dashboard does not query any of this
live — a batch export step materializes the small, pre-known slice of
results it needs into JSON, which `ingestion/push_to_supabase.py` pushes
to Supabase; the deployed dashboard reads from there via the Render API,
polling every 60 seconds, rather than reading the JSON file directly (see
the Application Layer section above for the full chain and its free-tier
constraints).
