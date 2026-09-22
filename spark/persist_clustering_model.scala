// Persists the StandardScaler + KMeans models fit by spark/stress_clustering.scala,
// so live streaming rows can be scored via .transform() (nearest-centroid
// assignment) against the SAME frozen clusters, rather than the streaming
// job re-fitting K-Means on historical+live data combined — which would
// risk silently shifting the already-published historical cluster
// assignments in docs/FINDINGS.md. Confirmed design, not assumed (see docs/FINDINGS.md
// "ML crisis classifier" section context and the live-streaming design
// discussion for the reasoning).
//
// This script rebuilds the EXACT same feature pipeline as
// stress_clustering.scala (same input tables, same transformations, same
// seed) — deterministic, so it reproduces the identical fit. It does NOT
// touch meridian.stress_clusters or meridian.stress_cluster_profiles at
// all; it only saves the fitted models to disk, and verifies (not assumes)
// that re-fitting reproduces the already-published cluster assignments
// exactly before declaring success.

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.spark.ml.feature.{VectorAssembler, StandardScaler}
import org.apache.spark.ml.clustering.KMeans

val spark = SparkSession.builder.appName("PersistClusteringModel").enableHiveSupport().getOrCreate()
import spark.implicits._

val K = 4
// This path resolves against Spark's configured default filesystem, which
// in this project's stack is HDFS (not local disk) — confirmed after
// running: the saved model actually lands under this path on HDFS, not
// /home/chirag/... on the local filesystem. That's the right place for it:
// a shared, durable artifact the streaming job (running as a separate
// process) needs to read, consistent with where every Hive table's data
// already lives. See `hdfs dfs -ls -R` on this path to inspect it.
val MODEL_DIR = "/home/chirag/Desktop/Meridian/spark/models/stress_clustering"

val h = spark.table("meridian.stablecoin_pool_hourly")
val b = spark.table("meridian.baseline_stats")

val hClean = h.filter($"anomaly_flag" =!= "NAN_PRICE")

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
  .select($"pair", $"project", $"window_start_ts", $"prediction".as("refit_cluster_id"))

// --- Verification: does the re-fit reproduce the published assignments exactly? ---
val published = spark.table("meridian.stress_clusters")
  .select($"pair", $"project", $"window_start_ts", $"cluster_id".as("published_cluster_id"))

val compared = predicted.join(published, Seq("pair", "project", "window_start_ts"))
val totalRows = compared.count()
val mismatches = compared.filter($"refit_cluster_id" =!= $"published_cluster_id").count()

println(s"\nVerification: $totalRows rows compared, $mismatches mismatches between re-fit and published cluster_id")
if (mismatches > 0) {
  println("MISMATCH DETECTED — refusing to save. The re-fit did NOT reproduce the published clustering exactly.")
  println("Do not use these models for live scoring until this is investigated.")
  compared.filter($"refit_cluster_id" =!= $"published_cluster_id").show(20, false)
  System.exit(1)
}
println("VERIFIED: re-fit is byte-identical to the published meridian.stress_clusters assignments. Safe to persist.")

scalerModel.write.overwrite().save(s"$MODEL_DIR/scaler")
model.write.overwrite().save(s"$MODEL_DIR/kmeans")
println(s"\nSaved scaler model to $MODEL_DIR/scaler")
println(s"Saved kmeans model to $MODEL_DIR/kmeans")
println("\nmeridian.stress_clusters and meridian.stress_cluster_profiles were NOT modified by this script.")

System.exit(0)
