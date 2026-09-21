// Stress-signature clustering (K-Means via MLlib) over Meridian's hourly
// pool data. Design decided and confirmed with the user before writing this
// (see FINDINGS.md for the full report: feature computability, UST-handling
// approach, row counts, and k-selection justification) — not written
// speculatively.
//
// Unit of clustering: each (pair, project, hour) row from
// meridian.stablecoin_pool_hourly — not the 2 crisis events themselves,
// too small an n to cluster.
//
// Two-path feature design (see hive/stress_clusters_schema.sql for the full
// rationale):
//   - RELIABLE pairs: price/volume/trade_count z-scores against that
//     pair/project's own baseline_stats (calm-window) mean/stddev.
//   - NO_RELIABLE_BASELINE (UST) pairs: price = deviation from the $1.00
//     peg; volume/trade_count = z-score against the pair's own FRESH
//     full-history mean/stddev (NOT baseline_stats' numbers, which are
//     contaminated by the same pre/post-collapse blend as price).
//
// The 4 NAN_PRICE rows are excluded (genuinely undefined 0/0). The 221
// ZERO_VALUE_TRADE rows (UST) are retained with price_dev imputed to -1.0.
// Zero UST rows are silently dropped.
//
// k=4: empirically chosen via elbow (WSSSE) + silhouette sweep over
// k=2..10, sanity-checked against the known USDC Mar 2023 / UST May 2022
// crisis windows. See FINDINGS.md for the full sweep and justification.

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.spark.ml.feature.{VectorAssembler, StandardScaler}
import org.apache.spark.ml.clustering.KMeans

val spark = SparkSession.builder.appName("StressClustering").enableHiveSupport().getOrCreate()
import spark.implicits._

val K = 4

val h = spark.table("meridian.stablecoin_pool_hourly")
val b = spark.table("meridian.baseline_stats")

val hClean = h.filter($"anomaly_flag" =!= "NAN_PRICE")
println(s"Rows after excluding NAN_PRICE: ${hClean.count()} (of ${h.count()} total)")

val ustFullStats = hClean
  .join(b.select("pair", "project", "baseline_status"), Seq("pair", "project"))
  .filter($"baseline_status" === "NO_RELIABLE_BASELINE")
  .groupBy($"pair", $"project")
  .agg(
    avg($"volume_usd").as("ust_mean_volume"),
    stddev($"volume_usd").as("ust_stddev_volume"),
    avg($"trade_count".cast("double")).as("ust_mean_trades"),
    stddev($"trade_count".cast("double")).as("ust_stddev_trades")
  )

val joined = hClean
  .join(b, Seq("pair", "project"))
  .join(ustFullStats, Seq("pair", "project"), "left")

val withFeatures = joined
  .withColumn("price_dev",
    when($"baseline_status" === "RELIABLE" && $"is_valid_price" === true,
      ($"implied_price" - $"mean_price") / $"stddev_price")
    .when($"baseline_status" === "NO_RELIABLE_BASELINE" && $"is_valid_price" === true,
      $"implied_price" - lit(1.0))
    .when($"baseline_status" === "NO_RELIABLE_BASELINE" && $"is_valid_price" === false,
      lit(-1.0))
    .otherwise(lit(0.0))
  )
  .withColumn("volume_dev",
    when($"baseline_status" === "RELIABLE",
      ($"volume_usd" - $"mean_volume_usd") / $"stddev_volume_usd")
    .otherwise(($"volume_usd" - $"ust_mean_volume") / $"ust_stddev_volume")
  )
  .withColumn("trade_count_dev",
    when($"baseline_status" === "RELIABLE",
      ($"trade_count".cast("double") - $"mean_trade_count") / $"stddev_trade_count")
    .otherwise(($"trade_count".cast("double") - $"ust_mean_trades") / $"ust_stddev_trades")
  )
  .withColumn("anomaly_binary", when($"anomaly_flag" =!= "NONE", lit(1.0)).otherwise(lit(0.0)))
  .filter($"price_dev".isNotNull && $"volume_dev".isNotNull && $"trade_count_dev".isNotNull)

println(s"Rows with complete features feeding clustering: ${withFeatures.count()}")

val assembler = new VectorAssembler()
  .setInputCols(Array("price_dev", "volume_dev", "trade_count_dev", "anomaly_binary"))
  .setOutputCol("raw_features")
val assembled = assembler.transform(withFeatures)

val scaler = new StandardScaler()
  .setInputCol("raw_features").setOutputCol("features")
  .setWithMean(true).setWithStd(true)
val scalerModel = scaler.fit(assembled)
val scaled = scalerModel.transform(assembled).cache()

val km = new KMeans().setK(K).setSeed(42L).setFeaturesCol("features")
val model = km.fit(scaled)
val predicted = model.transform(scaled)

val rowsOut = predicted
  .select(
    $"pair", $"project", $"window_start_ts", $"dt", $"baseline_status",
    $"price_dev", $"volume_dev", $"trade_count_dev", $"anomaly_flag", $"anomaly_binary",
    lit(K).as("k"), $"prediction".as("cluster_id")
  )
  .withColumn("computed_at", current_timestamp())

rowsOut.createOrReplaceTempView("stress_clusters_computed")
spark.sql("""
  INSERT INTO TABLE meridian.stress_clusters
  SELECT pair, project, window_start_ts, dt, baseline_status,
         price_dev, volume_dev, trade_count_dev, anomaly_flag, anomaly_binary,
         k, cluster_id, computed_at
  FROM stress_clusters_computed
""")

val labeled = predicted.withColumn("period_label",
  when($"dt" >= "2023-03-08" && $"dt" <= "2023-03-15", lit("USDC_CRISIS"))
  .when($"dt" >= "2022-05-07" && $"dt" <= "2022-05-16", lit("UST_CRISIS"))
  .otherwise(lit("OTHER"))
)

val profilesOut = labeled.groupBy($"prediction".as("cluster_id"))
  .agg(
    count("*").as("n_rows"),
    avg("price_dev").as("avg_price_dev"),
    avg("volume_dev").as("avg_volume_dev"),
    avg("trade_count_dev").as("avg_trade_count_dev"),
    avg("anomaly_binary").as("avg_anomaly_binary"),
    avg(when($"baseline_status" === "NO_RELIABLE_BASELINE", 1.0).otherwise(0.0)).as("pct_ust_rows"),
    sum(when($"period_label" === "USDC_CRISIS", 1).otherwise(0)).as("n_usdc_crisis_rows"),
    sum(when($"period_label" === "UST_CRISIS", 1).otherwise(0)).as("n_ust_crisis_rows")
  )
  .withColumn("k", lit(K))
  .withColumn("computed_at", current_timestamp())

profilesOut.createOrReplaceTempView("stress_cluster_profiles_computed")
spark.sql("""
  INSERT INTO TABLE meridian.stress_cluster_profiles
  SELECT k, cluster_id, n_rows, avg_price_dev, avg_volume_dev, avg_trade_count_dev,
         avg_anomaly_binary, pct_ust_rows, n_usdc_crisis_rows, n_ust_crisis_rows, computed_at
  FROM stress_cluster_profiles_computed
""")

println("\n=== CLUSTER PROFILES (k=4) ===")
spark.sql("""
  SELECT cluster_id, n_rows, avg_price_dev, avg_volume_dev, avg_trade_count_dev,
         avg_anomaly_binary, pct_ust_rows, n_usdc_crisis_rows, n_ust_crisis_rows
  FROM meridian.stress_cluster_profiles
  ORDER BY cluster_id
""").show(20, false)

System.exit(0)
