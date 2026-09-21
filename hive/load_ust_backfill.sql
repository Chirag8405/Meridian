-- Loads the UST historical backfill (ingestion/dune_ust_backfill.py output)
-- into the SAME meridian.stablecoin_pool_hourly table used by the
-- USDC/USDT/DAI backfill — purely additive via new pair values
-- (UST_USDC, UST_USDT, UST_DAI), no schema changes, no existing
-- partitions touched.

SET hive.exec.dynamic.partition.mode=nonstrict;
SET hive.exec.dynamic.partition=true;
SET hive.exec.max.dynamic.partitions.pernode=10000;
SET hive.exec.max.dynamic.partitions=10000;

CREATE EXTERNAL TABLE IF NOT EXISTS meridian.stablecoin_pool_hourly_ust_staging (
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
LOCATION '/user/chirag/meridian/staging/stablecoin_pool_hourly_ust_backfill';

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
FROM meridian.stablecoin_pool_hourly_ust_staging;
