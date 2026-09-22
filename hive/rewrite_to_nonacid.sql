-- Rewrites meridian.stablecoin_pool_hourly from its current ACID
-- (transactional) state into a fresh plain managed table, fixing the
-- implied_price nulling gap in the same pass (the 221 ZERO_VALUE_TRADE rows
-- currently have implied_price=0.0 instead of NULL).
--
-- Why not just compact the ACID table: compaction fixes the query speed but
-- leaves the table permanently ACID — ongoing per-query overhead (needing
-- hive.support.concurrency/txn.manager/input.format set every session) and,
-- more importantly, a real risk to Spark's ability to read it cleanly later.
-- Spark's Hive integration has known limitations with Hive ACID tables, and
-- this project already invested real effort getting Spark 3.5.5 to speak to
-- Hive 3.1.3's metastore correctly (see docs/SETUP.md / CLAUDE.md) — not worth
-- risking for the analytics work ahead (PageRank, clustering, MLlib).

-- Reading FROM the current ACID table needs these settings.
SET hive.support.concurrency=true;
SET hive.txn.manager=org.apache.hadoop.hive.ql.lockmgr.DbTxnManager;
SET hive.input.format=org.apache.hadoop.hive.ql.io.HiveInputFormat;
SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.exec.dynamic.partition=true;
SET hive.exec.max.dynamic.partitions.pernode=10000;
SET hive.exec.max.dynamic.partitions=10000;

-- Plain managed table, identical schema, no transactional property.
CREATE TABLE meridian.stablecoin_pool_hourly_v2 (
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

INSERT INTO TABLE meridian.stablecoin_pool_hourly_v2
PARTITION (pair, dt)
SELECT
    window_start_ts,
    project,
    pool_address,
    blockchain,
    trade_count,
    volume_usd,
    CASE WHEN is_valid_price = false THEN NULL ELSE implied_price END AS implied_price,
    raw_price_value,
    is_valid_price,
    anomaly_flag,
    source,
    ingested_at,
    pair,
    dt
FROM meridian.stablecoin_pool_hourly;

-- Swap step deliberately NOT included here — run hive/swap_in_nonacid.sql
-- separately, only after verifying stablecoin_pool_hourly_v2's row count
-- and data look correct. Don't drop the only copy of the source table
-- before confirming the rewrite actually worked.
