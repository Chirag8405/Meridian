-- PageRank result tables for the bipartite wallet/pool influence analysis
-- (see spark/wallet_pagerank.scala and ARCHITECTURE.md's Analytics layer
-- section for the bipartite construction rationale). Reads from
-- meridian.wallet_trades_raw (hive/wallet_trades_raw_schema.sql).

-- One row per node per window (a wallet or pool's PageRank score within a
-- specific overall/calm/crisis window). NOT partitioned — this is Spark's
-- output, a few thousand rows per window at most, not a scan-heavy table.
CREATE TABLE IF NOT EXISTS meridian.wallet_pagerank (
    window_type        STRING    COMMENT 'OVERALL, CALM, or CRISIS',
    window_label        STRING    COMMENT 'ALL, USDC_CALM, USDC_MAR2023_CRISIS, UST_CALM, or UST_MAY2022_CRISIS',
    node_type            STRING    COMMENT 'WALLET or POOL',
    node_id               STRING    COMMENT 'Address (wallet or pool contract)',
    pagerank_score         DOUBLE    COMMENT 'Weighted PageRank score within this window (see script for the weighted-edge algorithm — GraphX''s built-in pageRank() does not support edge weights, so this is a custom Pregel-based implementation)',
    rank_within_window      INT       COMMENT '1 = highest-ranked node in this (window_label, node_type) group',
    computed_at               TIMESTAMP COMMENT 'When this row was computed'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');

-- Data-quality labels for addresses that turned out to matter (top-ranked
-- wallets checked for contract vs. EOA status). Populated by a follow-up
-- Python step (ingestion/wallet_contract_check.py) using Alchemy's
-- eth_getCode — NOT guessed from address-name pattern matching.
CREATE TABLE IF NOT EXISTS meridian.wallet_labels (
    address       STRING    COMMENT 'Wallet/contract address, lowercase',
    is_contract   BOOLEAN   COMMENT 'TRUE if eth_getCode returned non-empty bytecode at this address',
    label         STRING    COMMENT 'Best-effort identification (e.g. "1inch v4 Router") when found; NULL if unidentified',
    note          STRING    COMMENT 'Free-text context, e.g. which window/rank this address was checked for',
    checked_at    TIMESTAMP COMMENT 'When this address was checked'
)
STORED AS ORC
TBLPROPERTIES ('orc.compress'='ZLIB');
