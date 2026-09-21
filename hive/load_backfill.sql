-- Loads the Dune historical backfill (ingestion/dune_backfill.py output,
-- uploaded to HDFS at /user/chirag/meridian/staging/stablecoin_pool_hourly_backfill/)
-- into the partitioned meridian.stablecoin_pool_hourly table.
--
-- Two-step load: an external TEXTFILE staging table over the raw TSV, then
-- INSERT ... SELECT into the ORC target table with dynamic partitioning on
-- (pair, dt). Partition columns must be selected LAST for dynamic
-- partitioning to work.

SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.exec.dynamic.partition=true;
-- Default hive.exec.max.dynamic.partitions.pernode is 100; a 6-month
-- backfill across 2 pairs creates ~350+ (pair, dt) partitions, all from
-- this single-node pseudo-distributed cluster's one mapper.
SET hive.exec.max.dynamic.partitions.pernode=10000;
SET hive.exec.max.dynamic.partitions=10000;

CREATE EXTERNAL TABLE IF NOT EXISTS meridian.stablecoin_pool_hourly_staging (
    window_start_ts STRING,
    project         STRING,
    pool_address    STRING,
    blockchain      STRING,
    trade_count     BIGINT,
    volume_usd      DOUBLE,
    implied_price   DOUBLE,
    raw_price_value STRING,
    is_valid_price  BOOLEAN,
    anomaly_flag    STRING,
    source          STRING,
    ingested_at     STRING,
    pair            STRING,
    dt              STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\t'
NULL DEFINED AS '\\N'
STORED AS TEXTFILE
LOCATION '/user/chirag/meridian/staging/stablecoin_pool_hourly_backfill';

INSERT INTO TABLE meridian.stablecoin_pool_hourly
PARTITION (pair, dt)
SELECT
    CAST(window_start_ts AS TIMESTAMP),
    project,
    pool_address,
    blockchain,
    trade_count,
    volume_usd,
    implied_price,
    raw_price_value,
    is_valid_price,
    anomaly_flag,
    source,
    current_timestamp() AS ingested_at,
    pair,
    dt
FROM meridian.stablecoin_pool_hourly_staging;
