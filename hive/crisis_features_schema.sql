-- Feature table for the ML crisis classifier (spark/crisis_classifier.scala),
-- built to specifically address the rule-based baseline's documented
-- limitation: magnitude-only scoring with no concept of trend/trajectory
-- (see docs/FINDINGS.md, "Rule-based baseline risk score" section, item 2).
--
-- Design notes (flagged and confirmed with the user before implementing,
-- see docs/FINDINGS.md for the full report):
--
--   - Trend/velocity features use TIME-BASED windows, not row-count-based
--     ones. Real gaps exist in the hourly series (an hour only gets a row
--     if a qualifying trade happened in it) — as low as 17% coverage for
--     UST_DAI. A naive LAG()/row-count rolling window would silently
--     compute "hour-over-hour change" between rows that could be days
--     apart. price_severity_velocity is NULL (not zero, not a misleading
--     large number) when the previous row is more than 6 hours away or
--     doesn't exist — `trend_available` makes that explicit rather than
--     letting a downstream NULL-vs-zero ambiguity hide it.
--   - price_severity_rolling_mean_3h / price_severity_rolling_slope_3h use
--     a genuine time-based RANGE frame (INTERVAL 3 HOURS PRECEDING), so a
--     gap doesn't silently stretch the "3-hour window" to cover more or
--     less actual wall-clock time than intended.
--   - `label` (binary CALM=0/CRISIS=1) is grounded in independently-known
--     historical crisis date windows, NOT derived from cluster_id,
--     cluster_severity, or risk_score — using our own severity metrics as
--     ground truth would let a "beat the baseline" model partly learn to
--     just reproduce the baseline, invalidating the comparison. USDC:
--     CRISIS = 2023-03-08 to 2023-03-15 only (USDC's pre/post-crisis data
--     is genuinely calm, per docs/FINDINGS.md). UST: CRISIS = every row in the
--     dataset — UST_BUILDUP (pre-existing instability before the official
--     window) and UST_COLLAPSED (pinned near $0.03-0.05 after it) are
--     both CRISIS, not CALM, by the same "not genuinely safe" reasoning
--     confirmed with the user. This means UST contributes ZERO calm
--     examples anywhere — a direct, expected consequence of this
--     dataset's pre-existing NO_RELIABLE_BASELINE finding, not new.
--   - Features intentionally EXCLUDE cluster_severity and risk_score
--     (meridian.risk_scores_baseline) — both are hand-assigned/assembled
--     specifically to represent "how crisis-like is this," too close to
--     the label for a model meant to independently beat the baseline
--     rather than partly mimic it. price_severity and
--     volume_trade_severity ARE included — they're normalized magnitude
--     features (necessary for cross-path comparability), not assembled
--     severity judgments.

CREATE TABLE IF NOT EXISTS meridian.crisis_features (
    pair                          STRING    COMMENT 'Stablecoin pair, e.g. USDC_USDT',
    project                       STRING    COMMENT 'DEX/protocol, e.g. curve, uniswap_v2',
    window_start_ts               TIMESTAMP COMMENT 'Start of the hourly window',
    dt                            STRING    COMMENT 'Partition date, YYYY-MM-DD (UTC)',
    baseline_status               STRING    COMMENT 'RELIABLE or NO_RELIABLE_BASELINE',
    label                         INT       COMMENT '1=CRISIS, 0=CALM. Grounded in historical crisis date windows, not derived from any of our own severity metrics',
    price_severity                DOUBLE    COMMENT 'Reused from meridian.risk_scores_baseline — normalized [0,1] price deviation magnitude',
    volume_trade_severity         DOUBLE    COMMENT 'Reused from meridian.risk_scores_baseline — normalized [0,1] volume/trade_count deviation magnitude',
    wallet_concentration_severity DOUBLE    COMMENT 'Reused from meridian.risk_scores_baseline. 0.0 for all UST rows (zeroed by design, see that table''s schema notes)',
    cluster_id                    INT       COMMENT 'From meridian.stress_clusters (k=4) — unsupervised, never saw crisis labels, safe as an input feature',
    hours_since_prev              DOUBLE    COMMENT 'Elapsed hours to the previous row in this (pair, project) series. NULL for the first row in a series',
    price_severity_velocity       DOUBLE    COMMENT '(price_severity - previous price_severity) / hours_since_prev. NULL when hours_since_prev > 6 or the previous row does not exist',
    price_severity_rolling_mean_3h  DOUBLE  COMMENT 'Time-based rolling mean of price_severity over the trailing 3 wall-clock hours (RANGE frame, not row-count)',
    price_severity_rolling_slope_3h DOUBLE  COMMENT '(current price_severity - earliest price_severity in the trailing 3-hour window) / actual elapsed hours between them. NULL when no other row exists in that window',
    trend_available                BOOLEAN  COMMENT 'TRUE when price_severity_velocity is non-NULL (a genuine within-6h prior point exists). Used downstream to distinguish "no trend" from "trend unknown" rather than silently imputing',
    computed_at                    TIMESTAMP COMMENT 'When this row was computed'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');
