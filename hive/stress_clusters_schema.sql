-- Stress-signature clustering results (K-Means, see spark/stress_clustering.scala
-- and ARCHITECTURE.md's Analytics layer section for the design rationale).
--
-- Design notes (flagged and confirmed with the user before implementing):
--   - Unit of clustering is (pair, project, window_start_ts) from
--     meridian.stablecoin_pool_hourly, not the 2 crisis events themselves —
--     too small an n to cluster meaningfully.
--   - Two-path feature design, extended consistently across ALL THREE
--     deviation features (not just price) once it was found that
--     baseline_stats' own volume_usd/trade_count numbers for
--     NO_RELIABLE_BASELINE (UST) pairs are contaminated by the same
--     pre/post-collapse blended window as its price numbers:
--       - RELIABLE pairs: price/volume/trade_count z-scores against that
--         pair/project's own baseline_stats (calm-window) mean/stddev.
--       - NO_RELIABLE_BASELINE (UST) pairs: price = deviation from the
--         $1.00 peg (not a z-score, since no calm baseline exists to score
--         against); volume/trade_count = z-score against the pair's own
--         FRESH full-history mean/stddev (computed directly from the raw
--         hourly data, not from baseline_stats, to avoid reusing the same
--         contaminated numbers).
--   - The 4 NAN_PRICE rows (genuinely undefined 0/0, RELIABLE pairs only)
--     are excluded — no principled substitute value exists. The 221
--     ZERO_VALUE_TRADE rows (UST only) ARE included: price_dev is imputed
--     to -1.0 (price ~ 0, so peg deviation ~ -1.0 is directionally correct
--     and distinct from the z-score range used elsewhere). Zero UST rows
--     are silently dropped.
--   - k=4, chosen empirically (elbow + silhouette sweep k=2..10, see
--     FINDINGS.md) and sanity-checked against the known USDC Mar 2023 and
--     UST May 2022 crisis windows: it separates calm hours from a
--     mild-USDC-stress cluster, a severe-USDC-stress cluster, and a
--     distinct UST-stress cluster — i.e. it distinguishes stress *type and
--     severity*, not just a binary calm/crisis split.

-- One row per (pair, project, hour) — the clustering unit itself, with its
-- input features and resulting cluster assignment.
CREATE TABLE IF NOT EXISTS meridian.stress_clusters (
    pair              STRING    COMMENT 'Stablecoin pair, e.g. USDC_USDT',
    project           STRING    COMMENT 'DEX/protocol, e.g. curve, uniswap_v2',
    window_start_ts   TIMESTAMP COMMENT 'Start of the hourly window being clustered',
    dt                STRING    COMMENT 'Partition date of the source row, YYYY-MM-DD (UTC)',
    baseline_status   STRING    COMMENT 'RELIABLE or NO_RELIABLE_BASELINE — which feature path this row took',
    price_dev         DOUBLE    COMMENT 'RELIABLE: z-score vs baseline_stats mean_price. NO_RELIABLE_BASELINE: deviation from $1.00 peg (or -1.0 imputed for ZERO_VALUE_TRADE rows)',
    volume_dev        DOUBLE    COMMENT 'z-score vs baseline_stats mean_volume_usd (RELIABLE) or vs this pair''s own fresh full-history mean/stddev (NO_RELIABLE_BASELINE)',
    trade_count_dev   DOUBLE    COMMENT 'z-score vs baseline_stats mean_trade_count (RELIABLE) or vs this pair''s own fresh full-history mean/stddev (NO_RELIABLE_BASELINE)',
    anomaly_flag      STRING    COMMENT 'Source anomaly_flag carried through for context (controlled vocabulary, see hive/schema.sql)',
    anomaly_binary     DOUBLE    COMMENT '1.0 if anomaly_flag != NONE else 0.0 — the 4th clustering feature',
    k                 INT       COMMENT 'Number of clusters used for this run (4, empirically chosen — see FINDINGS.md)',
    cluster_id        INT       COMMENT 'Assigned cluster, 0..k-1. Meaningless on its own — join to meridian.stress_cluster_profiles for interpretation',
    computed_at       TIMESTAMP COMMENT 'When this row was computed'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');

-- One row per cluster — summary stats characterizing what each cluster_id
-- actually represents (a bare integer ID is not interpretable on its own;
-- this is the same pattern as meridian.wallet_labels characterizing
-- meridian.wallet_pagerank's node_ids).
CREATE TABLE IF NOT EXISTS meridian.stress_cluster_profiles (
    k                    INT       COMMENT 'Number of clusters for this run (4)',
    cluster_id           INT       COMMENT 'Cluster ID, 0..k-1',
    n_rows               BIGINT    COMMENT 'Number of (pair, project, hour) rows assigned to this cluster',
    avg_price_dev        DOUBLE    COMMENT 'Mean price_dev within this cluster',
    avg_volume_dev       DOUBLE    COMMENT 'Mean volume_dev within this cluster',
    avg_trade_count_dev  DOUBLE    COMMENT 'Mean trade_count_dev within this cluster',
    avg_anomaly_binary   DOUBLE    COMMENT 'Fraction of rows in this cluster with anomaly_flag != NONE',
    pct_ust_rows         DOUBLE    COMMENT 'Fraction of rows in this cluster from NO_RELIABLE_BASELINE (UST) pairs — helps identify coin-specific vs. general stress clusters',
    n_usdc_crisis_rows   BIGINT    COMMENT 'Rows in this cluster falling within the USDC_MAR2023 crisis window (2023-03-08 to 2023-03-15), for sanity-checking against a known event',
    n_ust_crisis_rows    BIGINT    COMMENT 'Rows in this cluster falling within the UST_MAY2022 crisis window (2022-05-07 to 2022-05-16), for sanity-checking against a known event',
    computed_at          TIMESTAMP COMMENT 'When this row was computed'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');
