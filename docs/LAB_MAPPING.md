# Lab Mapping

Maps each BDA lab syllabus item to its corresponding Meridian component. Status as of 2026-10-25.
The project owner has confirmed the core BDA requirements are fulfilled; items below marked
"not required" were deliberately descoped, not forgotten. Rows without a status were not
re-audited when this table was refreshed.

| Lab # | Lab Topic | Meridian Component | Status |
|---|---|---|---|
| 1 | HDFS Basics | Raw on-chain data, price feed storage | In use (Hive tables live on HDFS) |
| 2 | MapReduce word count | (none) | Not required |
| 3 | MapReduce: matrix mult, aggregates, joins, sort, search | Aggregate liquidity/price-deviation stats per stablecoin/day | Done in Spark (`spark/baseline_crisis_stats.scala`); dedicated MapReduce jobs not required |
| 4 | Sqoop | Transfer curated historical depeg incident records from staging DB | See `sqoop/` |
| 5 | NoSQL (MongoDB) | Pool-state JSON, exchange price API responses | Not re-audited |
| 6 | Hive descriptive analytics | Schema partitioned by stablecoin/chain/date | Done (`hive/schema.sql`, partitioned by pair and date) |
| 7 | Stream algorithm (DGIM/Bloom/FM) | (was: Bloom filter dedup, DGIM spike detection) | Not required |
| 8 | Spark iterative (PageRank/K-Means) | PageRank on the wallet/pool network; K-Means on hourly stress signatures | Done (`spark/wallet_pagerank.scala`, `spark/stress_clustering.scala`) |
| 9 | CURE/Canopy clustering | (K-Means is used instead) | Not required |
| 10 | Dashboard (Hive+Impala) | Live risk-score dashboard per stablecoin | Done as a Next.js dashboard on Supabase/Render (the dashboard never queries Hive live; see ARCHITECTURE.md) |
| 11 | Streaming (Flume/Hive/PySpark) | Live on-chain pool-ratio/price stream (real, not simulated) | Done with Spark Structured Streaming (`spark/stream_alchemy_live.scala`) |
| 12 | MLlib + Spark | Depeg-risk classification model | Done (`spark/crisis_classifier.scala`; results in FINDINGS.md) |

## Open Items

None. The earlier open item (Lab 2 word count) is closed as not required.
