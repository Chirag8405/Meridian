# Lab Mapping

Maps each BDA lab syllabus item to its corresponding Meridian component.

| Lab # | Lab Topic | Meridian Component |
|---|---|---|
| 1 | HDFS Basics | Raw on-chain data, price feed storage |
| 2 | MapReduce word count | **(note: needs a text-based sub-component if required — flag as open item)** |
| 3 | MapReduce: matrix mult, aggregates, joins, sort, search | Aggregate liquidity/price-deviation stats per stablecoin/day |
| 4 | Sqoop | Transfer curated historical depeg incident records from staging DB |
| 5 | NoSQL (MongoDB) | Pool-state JSON, exchange price API responses |
| 6 | Hive descriptive analytics | Schema partitioned by stablecoin/chain/date |
| 7 | Stream algorithm (DGIM/Bloom/FM) | Bloom filter for dedup of incoming pool-update events; DGIM for sliding-window redemption-rate spikes |
| 8 | Spark iterative (PageRank/K-Means) | PageRank on wallet/pool influence network |
| 9 | CURE/Canopy clustering | Cluster historical depeg events by stress-pattern signature |
| 10 | Dashboard (Hive+Impala) | Live risk-score dashboard per stablecoin |
| 11 | Streaming (Flume/Hive/PySpark) | Live on-chain pool-ratio/price stream (real, not simulated) |
| 12 | MLlib + Spark | Depeg-risk classification/regression model |

## Open Items

- **Lab 2 (word count) is not yet mapped.** Needs a decision on whether to
  satisfy it separately or find a natural text corpus for the project domain
  (e.g., word count over on-chain transaction memo fields or a curated
  incident-report corpus). See [SCOPE.md](SCOPE.md) for pending decisions.
