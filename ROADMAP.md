# Roadmap

Phased checklist for Meridian.

- [ ] Finalize data source decision (see pending items in [SCOPE.md](SCOPE.md))
- [ ] Data ingestion scripts → HDFS
- [ ] Hive schema design + partitioning
- [ ] MapReduce baseline statistics jobs
- [ ] Resolve lab 2 (word count) mapping
- [ ] Spark: PageRank on wallet/pool network
- [ ] Spark: CURE/Canopy clustering of depeg events
- [ ] Data stream algorithm implementation (Bloom filter / DGIM)
- [ ] Spark Structured Streaming: live pool-ratio/price monitoring
- [ ] MLlib depeg-risk model, validated against UST/USDC historical cases
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
- [ ] Dashboard
- [ ] (Deferred) GenAI component decision and integration
