-- Wallet-level trade staging table — raw per-trade data (taker/tx_from/
-- tx_to + trade fields) pulled via ingestion/dune_wallet_pull.py, feeding
-- the bipartite wallet/pool PageRank analysis (see
-- spark/wallet_pagerank.scala and hive/wallet_pagerank_schema.sql for the
-- downstream result tables).

CREATE EXTERNAL TABLE IF NOT EXISTS meridian.wallet_trades_raw (
    taker        STRING COMMENT 'Wallet address that executed the swap (Dune-resolved taker) — used as wallet identity in the bipartite graph',
    tx_from      STRING COMMENT 'EOA that signed the transaction (may differ from taker if routed through a contract)',
    tx_to        STRING COMMENT 'Contract the transaction was sent to — often a router/aggregator, not the pool directly',
    pool_address STRING COMMENT 'The pool contract traded against',
    amount_usd   DOUBLE COMMENT 'USD value of this individual trade',
    block_time   STRING COMMENT 'Trade timestamp',
    dt           STRING COMMENT 'Trade date, YYYY-MM-DD'
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '\t'
NULL DEFINED AS '\\N'
STORED AS TEXTFILE
LOCATION '/user/chirag/meridian/staging/wallet_trades';
