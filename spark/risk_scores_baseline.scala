// Rule-based/heuristic baseline risk score — built BEFORE any ML model
// training, so a trained model has something concrete to validate against.
// Design decided and confirmed with the user before writing this (see
// FINDINGS.md for the full report and hive/risk_scores_baseline_schema.sql
// for the per-component rationale) — not written speculatively.
//
// risk_score (0-100) = 100 * (
//   0.40 * price_severity +
//   0.25 * volume_trade_severity +
//   0.15 * cluster_severity +
//   0.20 * wallet_concentration_severity
// )
//
// All four components are independently normalized to [0,1] first, because
// the underlying features aren't comparable in raw units across the
// RELIABLE/NO_RELIABLE_BASELINE(UST) paths (see meridian.stress_clusters).

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._

val spark = SparkSession.builder.appName("RiskScoresBaseline").enableHiveSupport().getOrCreate()
import spark.implicits._

val PRICE_CAP_RELIABLE = 20.0
val VOLTRADE_CAP_RELIABLE = 20.0
val VOLTRADE_CAP_UST = 8.0

val sc = spark.table("meridian.stress_clusters")

// Cluster severity lookup, grounded in the actual per-cluster raw-price
// profile (see hive/risk_scores_baseline_schema.sql notes) — cluster 3
// (UST zero-value-trade signature) ranks above cluster 2 (severe USDC,
// highest z-score) because it represents a total, not partial, depeg.
val clusterSeverity = Map(0 -> 0.05, 1 -> 0.5, 2 -> 0.85, 3 -> 1.0)
val clusterSeverityUdf = udf((c: Int) => clusterSeverity.getOrElse(c, 0.0))

// Wallet-concentration lookup: recomputed live from meridian.wallet_pagerank
// rather than hardcoded, so this stays correct if that table is ever
// recomputed. USDC_CALM/USDC_MAR2023_CRISIS and UST_CALM/UST_MAY2022_CRISIS
// are each complete, non-overlapping partitions of their coin family's full
// date range (see spark/wallet_pagerank.scala's WindowDef definitions), so
// every RELIABLE row maps cleanly to exactly one of the two USDC windows by
// whether its dt falls in the crisis range.
val wp = spark.table("meridian.wallet_pagerank").filter($"node_type" === "WALLET")
val concByWindow = wp.groupBy("window_label")
  .agg(
    sum("pagerank_score").as("total_mass"),
    sum(when($"rank_within_window" <= 10, $"pagerank_score").otherwise(0.0)).as("top10_mass")
  )
  .withColumn("pct_top10", $"top10_mass" / $"total_mass")
  .select("window_label", "pct_top10")
  .collect()
  .map(r => r.getString(0) -> r.getDouble(1))
  .toMap

val usdcCalmConc = concByWindow("USDC_CALM")
val usdcCrisisConc = concByWindow("USDC_MAR2023_CRISIS")

println(s"USDC_CALM concentration: $usdcCalmConc, USDC_MAR2023_CRISIS concentration: $usdcCrisisConc")

val withScores = sc
  .withColumn("price_severity",
    when($"baseline_status" === "RELIABLE", least(abs($"price_dev") / lit(PRICE_CAP_RELIABLE), lit(1.0)))
    .otherwise(least(abs($"price_dev"), lit(1.0)))
  )
  .withColumn("volume_trade_severity",
    when($"baseline_status" === "RELIABLE",
      (least(abs($"volume_dev") / lit(VOLTRADE_CAP_RELIABLE), lit(1.0)) +
       least(abs($"trade_count_dev") / lit(VOLTRADE_CAP_RELIABLE), lit(1.0))) / lit(2.0))
    .otherwise(
      (least(abs($"volume_dev") / lit(VOLTRADE_CAP_UST), lit(1.0)) +
       least(abs($"trade_count_dev") / lit(VOLTRADE_CAP_UST), lit(1.0))) / lit(2.0))
  )
  .withColumn("cluster_severity", clusterSeverityUdf($"cluster_id"))
  .withColumn("wallet_concentration_severity",
    when($"baseline_status" === "RELIABLE" && $"dt" >= "2023-03-08" && $"dt" <= "2023-03-15", lit(usdcCrisisConc))
    .when($"baseline_status" === "RELIABLE", lit(usdcCalmConc))
    .otherwise(lit(0.0)) // zeroed for UST — concentration signal not validated for that coin, see schema notes
  )
  .withColumn("risk_score",
    lit(100.0) * (
      lit(0.40) * $"price_severity" +
      lit(0.25) * $"volume_trade_severity" +
      lit(0.15) * $"cluster_severity" +
      lit(0.20) * $"wallet_concentration_severity"
    )
  )
  .withColumn("computed_at", current_timestamp())

val rowsOut = withScores.select(
  $"pair", $"project", $"window_start_ts", $"dt", $"baseline_status", $"cluster_id",
  $"price_severity", $"volume_trade_severity", $"cluster_severity", $"wallet_concentration_severity",
  $"risk_score", $"computed_at"
)

rowsOut.createOrReplaceTempView("risk_scores_computed")
spark.sql("""
  INSERT INTO TABLE meridian.risk_scores_baseline
  SELECT pair, project, window_start_ts, dt, baseline_status, cluster_id,
         price_severity, volume_trade_severity, cluster_severity, wallet_concentration_severity,
         risk_score, computed_at
  FROM risk_scores_computed
""")

println(s"\nRows scored: ${rowsOut.count()}")

// Validation: known-calm vs. known-crisis score distributions.
val labeled = spark.table("meridian.risk_scores_baseline").withColumn("period_label",
  when($"baseline_status" === "RELIABLE" && $"dt" >= "2023-03-08" && $"dt" <= "2023-03-15", lit("USDC_CRISIS"))
  .when($"baseline_status" === "NO_RELIABLE_BASELINE" && $"dt" >= "2022-05-07" && $"dt" <= "2022-05-16", lit("UST_CRISIS"))
  .when($"baseline_status" === "RELIABLE", lit("RELIABLE_CALM"))
  .otherwise(lit("UST_OTHER"))
)

println("\n=== VALIDATION: risk_score distribution, RELIABLE-calm vs. known crisis windows ===")
labeled.groupBy("period_label").agg(
  count("*").as("n"),
  round(avg("risk_score"), 2).as("avg_score"),
  round(expr("percentile_approx(risk_score, 0.5)"), 2).as("median_score"),
  round(min("risk_score"), 2).as("min_score"),
  round(max("risk_score"), 2).as("max_score"),
  round(expr("percentile_approx(risk_score, 0.9)"), 2).as("p90_score")
).orderBy("period_label").show(20, false)

System.exit(0)
