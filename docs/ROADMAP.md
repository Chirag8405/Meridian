# Roadmap

Phased checklist for Meridian.

- [x] Data source decision (resolved: Dune historical + Alchemy live; see [SCOPE.md](SCOPE.md))
- [x] Data ingestion scripts → HDFS (`ingestion/`, `hive/load_backfill.sql`)
- [x] Hive schema design + partitioning (`hive/schema.sql`, partitioned by pair and date)
- [x] Baseline statistics (`spark/baseline_crisis_stats.scala`)
- [x] Spark: PageRank on the wallet/pool network (`spark/wallet_pagerank.scala`)
- [x] Spark: K-Means clustering of hourly stress signatures (`spark/stress_clustering.scala`)
- [x] Spark Structured Streaming: live pool-ratio/price monitoring
      (`spark/stream_alchemy_live.scala` + `ingestion/alchemy_live_feed.py`
      running under systemd `--user` services — see ARCHITECTURE.md's
      Analytics layer and SETUP.md's "Live streaming" section). Scores
      live rows via the frozen K-Means model (never re-fits — see
      FINDINGS.md's "Guarantee" section). Surfaced on the dashboard's
      "Live now" and "Recent activity" sections.
- [x] MLlib depeg-risk model, validated against UST/USDC historical cases
      - Validate against `meridian.risk_scores_baseline` (the rule-based
        baseline, see FINDINGS.md), not just against the raw historical
        cases directly — it's the concrete point of comparison this was
        built for.
      - Must include a trend/velocity feature (e.g. hour-over-hour or
        rolling change in price_dev/price_severity), not just
        point-in-time deviation. The baseline's known limitation (FINDINGS.md:
        "Rule-based baseline risk score") is that pure magnitude-of-
        deviation scoring can't tell "actively destabilizing" from
        "already fully collapsed and static" — it scored UST's dead
        post-collapse period (avg price_severity 0.967) higher than its
        actual pre-crisis buildup (0.475), backwards for an early-warning
        use case. A trend/velocity feature is a concrete, demonstrable way
        the trained model should outperform the baseline, not a generic
        "ML is fancier" comparison.
- [x] Dashboard (Vercel + Render + Supabase; see ARCHITECTURE.md Application Layer)
- [x] GenAI: risk advisories, grounded assistant, offline evaluation (see GENAI_ASSISTANT_PLAN.md)
- [ ] GenAI: LLM-as-judge experiment (Part C): preparation merged, model runs pending
- [ ] GenAI: re-run the frozen test split after the post-evaluation fixes

## Descoped (decided 2026-10-25: not required; core BDA requirements are fulfilled)

- Dedicated MapReduce jobs (Hive itself runs on the MapReduce engine here; the project's own jobs are Spark)
- Lab 2 (MapReduce word count) and its text-corpus mapping
- Stream-algorithm implementation: Bloom filter / DGIM
- CURE/Canopy clustering (K-Means is used instead; see ARCHITECTURE.md)
- HBase and Zookeeper (descoped earlier; see SCOPE.md)

