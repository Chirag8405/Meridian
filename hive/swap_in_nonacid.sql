-- Run only after verifying meridian.stablecoin_pool_hourly_v2 (from
-- hive/rewrite_to_nonacid.sql) has the correct row count and data.
-- Drops the old ACID table (managed table — this deletes its underlying
-- data too) and renames the new plain table into its place.

DROP TABLE meridian.stablecoin_pool_hourly;
ALTER TABLE meridian.stablecoin_pool_hourly_v2 RENAME TO meridian.stablecoin_pool_hourly;
