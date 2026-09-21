-- Baseline vs. crisis statistics for Meridian's risk model.
--
-- Design notes (both flagged and confirmed with the user before
-- implementing, not assumed):
--   - Grouped by (pair, project), not just pair: Curve and Uniswap have
--     different liquidity/reliability characteristics, so their hourly
--     observations for the same pair are kept as separate distributions
--     rather than pooled into one.
--   - Deliberately NOT partitioned: these are small summary tables
--     (one row per pair/project/window combination, a handful of rows
--     total). Hive partitioning exists to prune large scans; partitioning
--     a table this size would create mostly-empty partition directories
--     for no benefit.
--   - Price statistics (mean/stddev/percentiles) are computed only over
--     rows where is_valid_price = TRUE — NaN/zero-value/degenerate rows
--     don't belong in a price distribution. volume_usd and trade_count
--     statistics use ALL rows regardless of price validity, since a
--     zero-value trade still represents real trade activity.
--   - small_sample_flag = TRUE when n_price_rows < 30 (a conventional
--     rough threshold below which stddev/percentile estimates start being
--     unreliable) — surfaced as data, not silently hidden.
--   - baseline_status / baseline_status_note: small_sample_flag catches too
--     FEW data points, but that's not the only way a baseline can be
--     unusable — UST_USDC/UST_USDT/UST_DAI all clear the n>=30 threshold
--     (59-223 rows) yet aren't reliable, because there's no genuine calm
--     period in the dataset's time range at all: the pre-crisis-window
--     sub-period already shows instability for two of the three pairs, and
--     the post-crisis-window sub-period is just UST sitting near-worthless,
--     not recovered. This is a distinct failure mode from small-sample —
--     the sample is fine, the underlying period just isn't calm. See
--     FINDINGS.md for the full sub-period breakdown per pair. Marked
--     explicitly (not left as an implicit gap) because a downstream risk
--     model can't tell "no baseline exists" from "baseline says this is
--     normal" unless the data says so.

CREATE TABLE IF NOT EXISTS meridian.baseline_stats (
    pair                STRING    COMMENT 'Stablecoin pair, e.g. USDC_USDT',
    project             STRING    COMMENT 'DEX/protocol, e.g. curve, uniswap_v2',
    n_price_rows        BIGINT    COMMENT 'Count of is_valid_price=TRUE rows feeding the price statistics',
    n_total_rows        BIGINT    COMMENT 'Count of all rows (any validity) feeding the volume/trade_count statistics',
    mean_price          DOUBLE    COMMENT 'Mean implied_price over valid-price rows, calm-market window only',
    stddev_price        DOUBLE    COMMENT 'Sample stddev of implied_price over valid-price rows, calm-market window only',
    p10_price           DOUBLE    COMMENT '10th percentile implied_price',
    p25_price           DOUBLE    COMMENT '25th percentile implied_price',
    p75_price           DOUBLE    COMMENT '75th percentile implied_price',
    p90_price           DOUBLE    COMMENT '90th percentile implied_price',
    mean_volume_usd     DOUBLE    COMMENT 'Mean hourly volume_usd, calm-market window only',
    stddev_volume_usd   DOUBLE    COMMENT 'Sample stddev of hourly volume_usd, calm-market window only',
    mean_trade_count    DOUBLE    COMMENT 'Mean hourly trade_count, calm-market window only',
    stddev_trade_count  DOUBLE    COMMENT 'Sample stddev of hourly trade_count, calm-market window only',
    small_sample_flag   BOOLEAN   COMMENT 'TRUE when n_price_rows < 30 — treat stddev/percentiles as unreliable',
    baseline_status      STRING    COMMENT 'RELIABLE or NO_RELIABLE_BASELINE. Distinct from small_sample_flag: a pair can have plenty of rows and still have no genuine calm period in the data (e.g. an algorithmic stablecoin mid-collapse for its entire history in this dataset).',
    baseline_status_note STRING    COMMENT 'Explanation when baseline_status != RELIABLE, e.g. sub-period mean/stddev breakdown showing no calm period exists. NULL when RELIABLE.',
    computed_at          TIMESTAMP COMMENT 'When this row was computed'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');

CREATE TABLE IF NOT EXISTS meridian.crisis_stats (
    pair                STRING    COMMENT 'Stablecoin pair, e.g. USDC_USDT',
    project             STRING    COMMENT 'DEX/protocol, e.g. curve, uniswap_v2',
    crisis_window       STRING    COMMENT 'USDC_MAR2023 or UST_MAY2022 — which crisis this row covers',
    crisis_start_dt     STRING    COMMENT 'Window start date (YYYY-MM-DD, inclusive)',
    crisis_end_dt       STRING    COMMENT 'Window end date (YYYY-MM-DD, inclusive)',
    n_price_rows        BIGINT    COMMENT 'Count of is_valid_price=TRUE rows feeding the price statistics',
    n_total_rows        BIGINT    COMMENT 'Count of all rows (any validity) feeding the volume/trade_count statistics',
    mean_price          DOUBLE    COMMENT 'Mean implied_price over valid-price rows, within this crisis window',
    stddev_price        DOUBLE    COMMENT 'Sample stddev of implied_price over valid-price rows, within this crisis window',
    p10_price           DOUBLE    COMMENT '10th percentile implied_price',
    p25_price           DOUBLE    COMMENT '25th percentile implied_price',
    p75_price           DOUBLE    COMMENT '75th percentile implied_price',
    p90_price           DOUBLE    COMMENT '90th percentile implied_price',
    mean_volume_usd     DOUBLE    COMMENT 'Mean hourly volume_usd, within this crisis window',
    stddev_volume_usd   DOUBLE    COMMENT 'Sample stddev of hourly volume_usd, within this crisis window',
    mean_trade_count    DOUBLE    COMMENT 'Mean hourly trade_count, within this crisis window',
    stddev_trade_count  DOUBLE    COMMENT 'Sample stddev of hourly trade_count, within this crisis window',
    small_sample_flag   BOOLEAN   COMMENT 'TRUE when n_price_rows < 30 — treat stddev/percentiles as unreliable',
    computed_at          TIMESTAMP COMMENT 'When this row was computed'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');
