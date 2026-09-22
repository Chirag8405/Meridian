// Builds meridian.crisis_features — trend/velocity features and ground-truth
// labels for the ML crisis classifier (spark/crisis_classifier.scala).
// Design decided and confirmed with the user before writing this (see
// docs/FINDINGS.md for the full report) — not written speculatively.

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._

val spark = SparkSession.builder.appName("CrisisFeatures").enableHiveSupport().getOrCreate()
import spark.implicits._

val rsb = spark.table("meridian.risk_scores_baseline").drop("cluster_id")
val sc = spark.table("meridian.stress_clusters").select("pair", "project", "window_start_ts", "cluster_id")

val base = rsb.join(sc, Seq("pair", "project", "window_start_ts"))
  .select($"pair", $"project", $"window_start_ts", $"dt", $"baseline_status",
          $"price_severity", $"volume_trade_severity", $"wallet_concentration_severity", $"cluster_id")

// Ground-truth label: from historically-known crisis date windows only —
// NOT from cluster_id/cluster_severity/risk_score. USDC's pre/post-crisis
// data is genuinely calm (docs/FINDINGS.md), so only the official window counts.
// UST has no genuine calm period anywhere in this dataset (the
// NO_RELIABLE_BASELINE finding) — confirmed with the user: every UST row
// is CRISIS, including the pre-window buildup and the post-window
// collapsed/pinned-near-zero period, since neither is genuinely safe.
val labeled = base.withColumn("label",
  when($"baseline_status" === "RELIABLE" && $"dt" >= "2023-03-08" && $"dt" <= "2023-03-15", lit(1))
  .when($"baseline_status" === "RELIABLE", lit(0))
  .otherwise(lit(1)) // all NO_RELIABLE_BASELINE (UST) rows
)

// Time-based trend/velocity, partitioned per (pair, project) time series.
// Real gaps exist (see hive/crisis_features_schema.sql) — using genuine
// elapsed-hours arithmetic and a RANGE (not ROW) frame so an uneven gap
// doesn't silently distort the "hour-over-hour" or "3-hour" framing.
labeled.createOrReplaceTempView("crisis_features_base")

val withTrend = spark.sql("""
  SELECT *,
    (unix_timestamp(window_start_ts) - unix_timestamp(
      LAG(window_start_ts) OVER (PARTITION BY pair, project ORDER BY window_start_ts)
    )) / 3600.0 AS hours_since_prev,
    price_severity - LAG(price_severity) OVER (PARTITION BY pair, project ORDER BY window_start_ts) AS price_severity_delta,
    AVG(price_severity) OVER (
      PARTITION BY pair, project ORDER BY window_start_ts
      RANGE BETWEEN INTERVAL 3 HOURS PRECEDING AND CURRENT ROW
    ) AS price_severity_rolling_mean_3h,
    FIRST_VALUE(price_severity) OVER (
      PARTITION BY pair, project ORDER BY window_start_ts
      RANGE BETWEEN INTERVAL 3 HOURS PRECEDING AND CURRENT ROW
    ) AS price_severity_earliest_3h,
    FIRST_VALUE(window_start_ts) OVER (
      PARTITION BY pair, project ORDER BY window_start_ts
      RANGE BETWEEN INTERVAL 3 HOURS PRECEDING AND CURRENT ROW
    ) AS ts_earliest_3h
  FROM crisis_features_base
""")

val withFinal = withTrend
  .withColumn("price_severity_velocity",
    when($"hours_since_prev".isNotNull && $"hours_since_prev" <= 6.0, $"price_severity_delta" / $"hours_since_prev")
    .otherwise(lit(null).cast("double"))
  )
  .withColumn("price_severity_rolling_slope_3h",
    when($"ts_earliest_3h" =!= $"window_start_ts",
      ($"price_severity" - $"price_severity_earliest_3h") /
      ((unix_timestamp($"window_start_ts") - unix_timestamp($"ts_earliest_3h")) / 3600.0))
    .otherwise(lit(null).cast("double"))
  )
  .withColumn("trend_available", $"price_severity_velocity".isNotNull)
  .withColumn("computed_at", current_timestamp())

val rowsOut = withFinal.select(
  $"pair", $"project", $"window_start_ts", $"dt", $"baseline_status", $"label",
  $"price_severity", $"volume_trade_severity", $"wallet_concentration_severity", $"cluster_id",
  $"hours_since_prev", $"price_severity_velocity",
  $"price_severity_rolling_mean_3h", $"price_severity_rolling_slope_3h",
  $"trend_available", $"computed_at"
)

rowsOut.createOrReplaceTempView("crisis_features_computed")
spark.sql("""
  INSERT INTO TABLE meridian.crisis_features
  SELECT pair, project, window_start_ts, dt, baseline_status, label,
         price_severity, volume_trade_severity, wallet_concentration_severity, cluster_id,
         hours_since_prev, price_severity_velocity,
         price_severity_rolling_mean_3h, price_severity_rolling_slope_3h,
         trend_available, computed_at
  FROM crisis_features_computed
""")

println(s"\nRows written: ${rowsOut.count()}")
println("\n=== Label distribution ===")
spark.sql("SELECT baseline_status, label, COUNT(*) FROM meridian.crisis_features GROUP BY baseline_status, label ORDER BY baseline_status, label").show(false)
println("\n=== trend_available rate ===")
spark.sql("SELECT baseline_status, trend_available, COUNT(*) FROM meridian.crisis_features GROUP BY baseline_status, trend_available ORDER BY baseline_status, trend_available").show(false)

System.exit(0)
