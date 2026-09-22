// Spark Structured Streaming consumer for the Alchemy live feed
// (ingestion/alchemy_live_feed.py). Design decided and confirmed with the
// user before writing this (see docs/FINDINGS.md/ARCHITECTURE.md for the full
// live-streaming design report) — not written speculatively.
//
// Architecture: no native WebSocket source exists in Structured Streaming
// (confirmed against Spark's docs) — the Python ingester (decode/anomaly
// logic reused verbatim, not reimplemented) writes small, atomically-
// renamed JSON files into a landing directory; this job watches that
// directory via the File source, aggregates to hourly grain (same shape
// as the batch pipeline), and appends into the SAME Hive tables the batch
// pipeline uses (meridian.stablecoin_pool_hourly, meridian.risk_scores_baseline)
// — same storage, but the dashboard presents this as a separate "current"
// view rather than splicing it into the historical crisis-timeline charts
// (confirmed design).
//
// GUARANTEE: live rows are scored via .transform() against the FROZEN
// K-Means centroids persisted by spark/persist_clustering_model.scala
// (verified byte-identical to the published meridian.stress_clusters
// assignments before being saved). This job NEVER re-fits K-Means on
// historical+live data combined — doing so would risk silently shifting
// the already-published historical cluster assignments documented in
// docs/FINDINGS.md (cluster 2: 12 rows, cluster 3: exactly the 221
// ZERO_VALUE_TRADE rows, etc.). Those numbers are frozen as of the
// original fit and this job will never alter them.
//
// Trigger: 10 minutes (ProcessingTime). Not fighting the same "avoid
// per-query launch overhead" concern as Hive-on-MapReduce elsewhere in
// this project — a Structured Streaming query is one long-running
// application, each micro-batch tick is cheap even when empty. 10 minutes
// is a freshness/UX choice matched to the known ~1-event/15-20min/pool
// rate, not a resource-conservation one.
//
// Watermark + append mode: emits each hourly window's aggregate exactly
// once, only after the watermark has definitively passed it — avoids the
// alternative (update mode) which would emit multiple partial rows for
// the same hour as more events arrive, which a plain (non-ACID) Hive
// table can't cleanly de-duplicate via INSERT INTO.

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.spark.sql.types._
import org.apache.spark.sql.streaming.Trigger
import org.apache.spark.ml.feature.{StandardScalerModel, VectorAssembler}
import org.apache.spark.ml.clustering.KMeansModel

val spark = SparkSession.builder.appName("StreamAlchemyLive").enableHiveSupport().getOrCreate()
import spark.implicits._

// No existing Spark script has written into stablecoin_pool_hourly's
// dynamic (pair, dt) partitioning before (only hive/load_backfill.sql has,
// via the Hive CLI, which sets these the same way) — set explicitly rather
// than assume Spark's Hive integration defaults match.
spark.sql("SET hive.exec.dynamic.partition.mode=nonstrict")
spark.sql("SET hive.exec.dynamic.partition=true")

// Local filesystem (file:// prefix required) — the Python ingester writes
// here directly, unrelated to Spark's HDFS default filesystem (confirmed
// this distinction matters: the persisted clustering model landed on HDFS
// when saved without an explicit scheme).
val LANDING_DIR = "file:///home/chirag/Desktop/Meridian/data/raw/alchemy_live_stream"
// HDFS (default filesystem, no file:// prefix) — durable checkpoint state,
// consistent with where the persisted model and all Hive data already live.
val CHECKPOINT_DIR = "/home/chirag/Desktop/Meridian/spark/checkpoints/stream_alchemy_live"
val MODEL_DIR = "/home/chirag/Desktop/Meridian/spark/models/stress_clustering"

val PRICE_CAP_RELIABLE = 20.0
val VOLTRADE_CAP_RELIABLE = 20.0
// Live tracking is USDC-only (UST is dead, no live pool activity — see
// design report), so only the RELIABLE-path caps are needed here.

// --- Load the frozen models and reference data ONCE, before starting the stream ---
val scalerModel = StandardScalerModel.load(s"$MODEL_DIR/scaler")
val kmeansModel = KMeansModel.load(s"$MODEL_DIR/kmeans")
println(s"Loaded frozen clustering model: ${kmeansModel.clusterCenters.length} centroids")

val baselineStats = spark.table("meridian.baseline_stats")
  .filter($"baseline_status" === "RELIABLE")
  .select("pair", "project", "mean_price", "stddev_price", "mean_volume_usd",
          "stddev_volume_usd", "mean_trade_count", "stddev_trade_count")
  .cache()
baselineStats.count()  // materialize the cache before the stream starts

val clusterSeverity = Map(0 -> 0.05, 1 -> 0.5, 2 -> 0.85, 3 -> 1.0)
val clusterSeverityUdf = udf((c: Int) => clusterSeverity.getOrElse(c, 0.0))

val wp = spark.table("meridian.wallet_pagerank").filter($"node_type" === "WALLET")
val usdcCalmConc = wp.filter($"window_label" === "USDC_CALM")
  .agg(
    sum("pagerank_score").as("total_mass"),
    sum(when($"rank_within_window" <= 10, $"pagerank_score").otherwise(0.0)).as("top10_mass")
  )
  .select(($"top10_mass" / $"total_mass").as("pct")).head().getDouble(0)
println(s"USDC_CALM wallet concentration (static, reused for all live rows): $usdcCalmConc")

// --- Streaming read ---
val eventSchema = StructType(Seq(
  StructField("event_ts", StringType, nullable = false),
  StructField("pair", StringType, nullable = true),
  StructField("project", StringType, nullable = false),
  StructField("pool_address", StringType, nullable = false),
  StructField("blockchain", StringType, nullable = false),
  StructField("event_type", StringType, nullable = false),
  StructField("source", StringType, nullable = false),
  StructField("volume_usd", DoubleType, nullable = true),
  StructField("implied_price", DoubleType, nullable = true),
  StructField("is_valid_price", BooleanType, nullable = true),
  StructField("anomaly_flag", StringType, nullable = true)
))

val rawStream = spark.readStream
  .schema(eventSchema)
  .option("maxFilesPerTrigger", 2000)  // generous — our landing files are small
  .json(LANDING_DIR)

// Only SWAP events with a tracked pair feed the hourly aggregate — SYNC/
// RESERVE_SNAPSHOT events are landed for future use but aren't part of the
// current Hive schema's scope (matching the historical Dune pipeline,
// which is trade-based only). pair IS NULL means a direct DAI<->USDT
// Curve swap, which the historical dataset never tracked either — same
// scope, not a new gap (see ingestion/alchemy_live_feed.py's docstring).
val trades = rawStream
  .filter($"event_type" === "SWAP" && $"pair".isNotNull)
  .withColumn("event_ts_parsed", to_timestamp($"event_ts"))
  .withWatermark("event_ts_parsed", "2 hours")

// Anomaly-flag priority for the one-flag-per-hour rollup: a fixed,
// documented, deterministic order — NOT a severity ranking (these are
// categorically different issue types, not points on one scale). Multiple
// distinct flags in the same hour is expected to be rare given the known
// low event rate, so this tie-break rarely matters in practice.
val anomalyPriority = Map(
  "ZERO_VALUE_TRADE" -> 5, "NAN_PRICE" -> 4, "ZERO_AMOUNT_LEG" -> 3,
  "MULTI_LEG_TRADE" -> 2, "AMBIGUOUS_NET_DIRECTION" -> 1, "NONE" -> 0
)
val anomalyPriorityUdf = udf((f: String) => anomalyPriority.getOrElse(f, 0))

val hourly = trades
  .withColumn("anomaly_priority", anomalyPriorityUdf($"anomaly_flag"))
  .groupBy(
    window($"event_ts_parsed", "1 hour").as("w"),
    $"pair", $"project", $"pool_address", $"blockchain"
  )
  .agg(
    count("*").as("trade_count"),
    sum("volume_usd").as("volume_usd"),
    avg(when($"is_valid_price" === true, $"implied_price")).as("implied_price"),
    max(struct($"anomaly_priority", $"anomaly_flag")).as("top_anomaly"),
    max(when($"source" === "alchemy_getlogs_replay", lit(1)).otherwise(lit(0))).as("had_replay")
  )
  .select(
    $"pair", $"project", $"pool_address", $"blockchain",
    $"w.start".as("window_start_ts"),
    date_format($"w.start", "yyyy-MM-dd").as("dt"),
    $"trade_count", $"volume_usd", $"implied_price",
    $"top_anomaly.anomaly_flag".as("anomaly_flag"),
    ($"implied_price".isNotNull).as("is_valid_price"),
    when($"had_replay" === 1, lit("alchemy_getlogs_replay")).otherwise(lit("alchemy_live")).as("source")
  )

// --- Per-micro-batch: write the hourly aggregate, then score it for
// risk_scores_baseline using the FROZEN clustering model (never re-fit). ---
def processBatch(batchDfRaw: org.apache.spark.sql.DataFrame, batchId: Long): Unit = {
  val batchDf = batchDfRaw.cache()  // read multiple times below (count, join, insert)
  val n = batchDf.count()
  if (n == 0) {
    println(s"[batch $batchId] no finalized hourly windows this trigger")
    return
  }
  println(s"[batch $batchId] $n finalized hourly window(s)")

  val poolHourlyOut = batchDf
    .withColumn("raw_price_value", lit(null).cast("string"))  // not meaningfully aggregatable, same as the original field-mapping notes
    .withColumn("ingested_at", current_timestamp())
  poolHourlyOut.createOrReplaceTempView(s"stream_hourly_batch_$batchId")
  batchDf.sparkSession.sql(s"""
    INSERT INTO TABLE meridian.stablecoin_pool_hourly
    PARTITION (pair, dt)
    SELECT window_start_ts, project, pool_address, blockchain, trade_count,
           volume_usd, implied_price, raw_price_value, is_valid_price,
           anomaly_flag, source, ingested_at, pair, dt
    FROM stream_hourly_batch_$batchId
  """)

  // Score via the frozen model — .transform() only, never .fit().
  val withBaseline = batchDf.join(baselineStats, Seq("pair", "project"))
    .withColumn("price_dev", ($"implied_price" - $"mean_price") / $"stddev_price")
    .withColumn("volume_dev", ($"volume_usd" - $"mean_volume_usd") / $"stddev_volume_usd")
    .withColumn("trade_count_dev", ($"trade_count".cast("double") - $"mean_trade_count") / $"stddev_trade_count")
    .withColumn("anomaly_binary", when($"anomaly_flag" =!= "NONE", lit(1.0)).otherwise(lit(0.0)))
    .filter($"price_dev".isNotNull && $"volume_dev".isNotNull && $"trade_count_dev".isNotNull)

  if (withBaseline.count() == 0) {
    println(s"[batch $batchId] no rows had a matching baseline_stats row (pair/project not in baseline) — nothing scored")
    return
  }

  val assembler = new VectorAssembler()
    .setInputCols(Array("price_dev", "volume_dev", "trade_count_dev", "anomaly_binary"))
    .setOutputCol("raw_features")
  val assembled = assembler.transform(withBaseline)
  val scaled = scalerModel.transform(assembled)
  val clustered = kmeansModel.transform(scaled).withColumnRenamed("prediction", "cluster_id")

  val scored = clustered
    .withColumn("price_severity", least(abs($"price_dev") / lit(PRICE_CAP_RELIABLE), lit(1.0)))
    .withColumn("volume_trade_severity",
      (least(abs($"volume_dev") / lit(VOLTRADE_CAP_RELIABLE), lit(1.0)) +
       least(abs($"trade_count_dev") / lit(VOLTRADE_CAP_RELIABLE), lit(1.0))) / lit(2.0))
    .withColumn("cluster_severity", clusterSeverityUdf($"cluster_id"))
    .withColumn("wallet_concentration_severity", lit(usdcCalmConc))
    .withColumn("risk_score",
      lit(100.0) * (
        lit(0.40) * $"price_severity" + lit(0.25) * $"volume_trade_severity" +
        lit(0.15) * $"cluster_severity" + lit(0.20) * $"wallet_concentration_severity"
      )
    )
    .withColumn("baseline_status", lit("RELIABLE"))
    .withColumn("computed_at", current_timestamp())

  scored.createOrReplaceTempView(s"stream_scored_batch_$batchId")
  batchDf.sparkSession.sql(s"""
    INSERT INTO TABLE meridian.risk_scores_baseline
    SELECT pair, project, window_start_ts, dt, baseline_status, cluster_id,
           price_severity, volume_trade_severity, cluster_severity, wallet_concentration_severity,
           risk_score, computed_at
    FROM stream_scored_batch_$batchId
  """)
  println(s"[batch $batchId] wrote ${poolHourlyOut.count()} rows to stablecoin_pool_hourly, " +
          s"${scored.count()} rows to risk_scores_baseline")
}

val query = hourly.writeStream
  .outputMode("append")
  .trigger(Trigger.ProcessingTime("10 minutes"))
  .option("checkpointLocation", CHECKPOINT_DIR)
  .foreachBatch(processBatch _)
  .start()

println("Streaming query started. Awaiting termination...")
query.awaitTermination()
