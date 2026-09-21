-- Meridian: stablecoin pool hourly stats
--
-- Source: Dune Analytics `dex.trades`, aggregated to hourly buckets per pool
-- (see ingestion/dune_test_pull.py for the query pattern this is built on).
--
-- Design notes:
--   - Partitioned by (pair, dt): we'll have multiple pools/pairs
--     (USDC/USDT, USDC/DAI, ...) across multiple DEXes (Curve, Uniswap),
--     and most queries will filter to one pair over a date range, so this
--     keeps partition pruning effective without exploding partition count
--     (a handful of pairs x ~daily partitions is a small, manageable number).
--   - `pool_address` and `project` are NOT partition columns even though
--     multiple pools can serve the same pair (e.g. a USDC/USDT pool on both
--     Curve and Uniswap) — partitioning on them too would fragment small
--     amounts of data across too many directories for little pruning benefit.
--     They stay as regular columns so a single pair-partition can hold
--     several pools' data side by side.
--   - Anomaly handling (requirement: never silently drop/filter degenerate
--     rows, e.g. the 2023-03-12 00:00 UTC NaN we found in the test pull,
--     likely a zero-amount trade leg feeding a division):
--       - `implied_price` is NULL when the source value wasn't a valid
--         finite number, but the row itself is still inserted.
--       - `raw_price_value` preserves the original source string (e.g.
--         "NaN") verbatim, so nothing is lost even when parsing fails.
--       - `is_valid_price` makes validity a first-class, indexable/queryable
--         boolean rather than relying on implicit NULL semantics.
--       - `anomaly_flag` gives a human-readable reason from a controlled
--         vocabulary, since "invalid" alone doesn't say *why* (thin
--         liquidity vs. a genuine zero-amount leg vs. something else we
--         haven't seen yet).
--   - ZERO_VALUE_TRADE vs. NAN_PRICE vs. ZERO_AMOUNT_LEG — three distinct
--     mechanisms, not the same thing wearing different names:
--       - NAN_PRICE: the price calculation itself was undefined (e.g. 0/0).
--       - ZERO_AMOUNT_LEG: a specific multi-leg swap decode case (see
--         alchemy_live_feed.py) where a leg's amount was zero.
--       - ZERO_VALUE_TRADE: implied_price = 0.0 AND volume_usd = 0.0
--         *together* — a real trade actually executed, but at a genuinely
--         zero/dust value (observed during the May 2022 UST collapse: 221
--         rows, none in the calm USDC/USDT/DAI data). Not a calculation
--         error — treated as not-a-usable-price (is_valid_price=FALSE,
--         implied_price set NULL, same as NAN_PRICE) because feature
--         engineering shouldn't treat "0.0" as a real price point, but the
--         row itself, and the fact that a zero-value trade happened at that
--         hour, is a potential crisis-severity signal worth keeping.
--         Exact 0.0 only, no near-zero threshold.

CREATE DATABASE IF NOT EXISTS meridian;

CREATE TABLE IF NOT EXISTS meridian.stablecoin_pool_hourly (
    window_start_ts TIMESTAMP COMMENT 'Start of the hourly aggregation window (UTC)',
    project         STRING    COMMENT 'DEX/protocol, e.g. curve, uniswap_v3',
    pool_address    STRING    COMMENT 'On-chain pool/contract address',
    blockchain      STRING    COMMENT 'e.g. ethereum',
    trade_count     BIGINT    COMMENT 'Number of qualifying swap trades in this hour',
    volume_usd      DOUBLE    COMMENT 'Total USD volume of qualifying trades in this hour',
    implied_price   DOUBLE    COMMENT 'Implied price of base token per quote token for this pair, e.g. USDC per USDT. NULL when is_valid_price = FALSE',
    raw_price_value STRING    COMMENT 'Original raw value from the source API before parsing (e.g. "NaN"), preserved verbatim for auditability',
    is_valid_price  BOOLEAN   COMMENT 'FALSE when the source returned a non-finite/degenerate price (e.g. NaN from a zero-amount trade leg). Rows are always kept regardless of this value.',
    anomaly_flag    STRING    COMMENT 'Controlled vocabulary: NONE, NAN_PRICE, ZERO_AMOUNT_LEG, ZERO_VALUE_TRADE, LOW_LIQUIDITY, MULTI_LEG_TRADE, AMBIGUOUS_NET_DIRECTION, OTHER',
    source          STRING    COMMENT 'Data source, e.g. dune',
    ingested_at     TIMESTAMP COMMENT 'When this row was loaded into Hive'
)
PARTITIONED BY (
    pair   STRING  COMMENT 'Stablecoin pair, e.g. USDC_USDT, USDC_DAI',
    dt     STRING  COMMENT 'Partition date, YYYY-MM-DD (UTC)'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');

-- Dynamic partitioning will be needed to load a full backfill without
-- specifying every (pair, dt) partition by hand:
--   SET hive.exec.dynamic.partition.mode=nonstrict;
--   SET hive.exec.dynamic.partition=true;

-- Example query this schema is designed to answer directly (no full table
-- scan needed thanks to partition pruning on pair + dt):
--
-- SELECT window_start_ts, project, implied_price, is_valid_price, anomaly_flag
-- FROM meridian.stablecoin_pool_hourly
-- WHERE pair = 'USDC_USDT'
--   AND dt BETWEEN '2023-03-09' AND '2023-03-13'
-- ORDER BY window_start_ts;
