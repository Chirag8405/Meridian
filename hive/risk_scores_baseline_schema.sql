-- Rule-based/heuristic baseline risk score, computed BEFORE any ML model
-- training — exists so a trained model has something concrete to validate
-- against, rather than training blind with no reference point.
--
-- Design notes (flagged and confirmed with the user before implementing,
-- see docs/FINDINGS.md for the full writeup and validation results):
--
--   - Four independently-normalized [0,1] components, weighted and summed
--     to a 0-100 risk_score:
--       1. price_severity   (weight 0.40) — normalized |price_dev|, reused
--          from meridian.stress_clusters. RELIABLE pairs: z-score, capped
--          at 20 (20+ sigma is already maximal anomaly). NO_RELIABLE_BASELINE
--          (UST) pairs: deviation from $1.00 peg, already naturally bounded
--          to [0,1] (price can't go below $0), no cap needed.
--       2. volume_trade_severity (weight 0.25) — average of normalized
--          |volume_dev| and |trade_count_dev|, also reused from
--          stress_clusters. RELIABLE cap=20, UST cap=8 — UST's cap is
--          deliberately smaller because its self-referential full-history
--          baseline (see hive/stress_clusters_schema.sql) already partly
--          absorbs crisis behavior into its own mean/stddev, so UST
--          z-scores are structurally smaller than USDC's for a comparably
--          severe event. Component 3 (cluster membership) compensates for
--          this muting at UST's most extreme hours.
--       3. cluster_severity (weight 0.15) — lookup table from
--          meridian.stress_clusters.cluster_id, grounded in the actual
--          per-cluster raw-price/volume/trade_count profile (not assumed):
--          cluster 0 (calm) = 0.05, cluster 1 (moderate USDC stress) = 0.5,
--          cluster 2 (severe USDC stress, most extreme z-score) = 0.85,
--          cluster 3 (UST zero-value-trade signature, literal $0 trades =
--          total peg failure) = 1.0. Cluster 3 ranks above cluster 2
--          despite a smaller raw price_dev value, because it represents a
--          categorically worse real-world outcome (complete, not partial,
--          depeg) — see docs/FINDINGS.md for the reasoning.
--       4. wallet_concentration_severity (weight 0.20) — top-10-wallet
--          PageRank mass % (meridian.wallet_pagerank) for the window this
--          row falls in, normalized /100. ONLY available at window
--          granularity (5 windows total: ALL, USDC_CALM,
--          USDC_MAR2023_CRISIS, UST_CALM, UST_MAY2022_CRISIS), not hourly
--          — broadcast per row via (baseline_status, dt-in-crisis-range?),
--          which is a clean, complete partition of each coin family's full
--          date range (see spark/wallet_pagerank.scala's window
--          definitions). ZEROED OUT for NO_RELIABLE_BASELINE (UST) rows:
--          the concentration signal is validated as risk-increasing for
--          USDC (12.83% calm -> 43.39% crisis) but INVERTED for UST
--          (60.56% "calm" -> 52.57% crisis) because UST_CALM inherits the
--          same baseline contamination documented in docs/FINDINGS.md — using
--          it for UST would encode a backwards signal for every UST row.
--
--   - Weights (0.40 / 0.25 / 0.15 / 0.20) deliberately keep cluster_severity
--     low relative to price/volume — cluster membership is DERIVED from
--     those same features (plus anomaly_binary) via K-Means, so a high
--     weight there would double-count the same underlying signal. Confirmed
--     with the user: reduce cluster weight vs. the original 0.35/0.20/0.30/0.15
--     proposal specifically to cut that redundancy.
--
--   - 0-100 scale (not 0-1): more legible in a report ("risk_score=87"),
--     and avoids implying a calibrated probability this rule-based score
--     was never validated to produce.

CREATE TABLE IF NOT EXISTS meridian.risk_scores_baseline (
    pair                          STRING    COMMENT 'Stablecoin pair, e.g. USDC_USDT',
    project                       STRING    COMMENT 'DEX/protocol, e.g. curve, uniswap_v2',
    window_start_ts               TIMESTAMP COMMENT 'Start of the hourly window being scored',
    dt                            STRING    COMMENT 'Partition date of the source row, YYYY-MM-DD (UTC)',
    baseline_status               STRING    COMMENT 'RELIABLE or NO_RELIABLE_BASELINE — which feature path this row took',
    cluster_id                    INT       COMMENT 'Cluster assignment from meridian.stress_clusters (k=4)',
    price_severity                DOUBLE    COMMENT 'Normalized [0,1] price deviation severity',
    volume_trade_severity         DOUBLE    COMMENT 'Normalized [0,1] average of volume and trade_count deviation severity',
    cluster_severity              DOUBLE    COMMENT 'Normalized [0,1] severity from cluster membership lookup',
    wallet_concentration_severity DOUBLE    COMMENT 'Normalized [0,1] top-10-wallet concentration for this row''s window. 0.0 for all NO_RELIABLE_BASELINE (UST) rows — signal not validated for that coin, see notes above',
    risk_score                    DOUBLE    COMMENT '0-100 composite: 100 * (0.40*price_severity + 0.25*volume_trade_severity + 0.15*cluster_severity + 0.20*wallet_concentration_severity)',
    computed_at                   TIMESTAMP COMMENT 'When this row was computed'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');
