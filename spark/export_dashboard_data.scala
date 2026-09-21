// Exports the small, pre-known slices of project data the dashboard needs
// into static JSON files under dashboard/data/. Not a general-purpose
// export — five fixed queries, one per dashboard section, matching exactly
// what the dashboard renders. Rerun manually after any pipeline update; see
// ARCHITECTURE.md's Application Layer section for why this is a batch
// export rather than the dashboard querying Hive live (measured 46-56s for
// a trivial single-table COUNT(*) even on a warmed-up cluster — Hive here
// runs on the MapReduce engine, chosen early in this project to avoid a
// Tez retry-loop bug, and MapReduce's per-query container/JVM startup cost
// dominates regardless of data volume).

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import java.io.PrintWriter
import java.time.Instant

val spark = SparkSession.builder.appName("ExportDashboardData").enableHiveSupport().getOrCreate()
import spark.implicits._

val OUT_DIR = "/home/chirag/Desktop/Meridian/dashboard/data"

def writeJson(name: String, json: String): Unit = {
  val pw = new PrintWriter(s"$OUT_DIR/$name")
  pw.write(json)
  pw.close()
  println(s"Wrote $OUT_DIR/$name")
}

def arrayJson(rows: Array[String]): String = rows.mkString("[", ",", "]")

// 1. Current risk: latest available row per (pair, project).
val rsb = spark.table("meridian.risk_scores_baseline").as("rsb")
val latest = rsb.groupBy("pair", "project").agg(max("window_start_ts").as("max_ts")).as("latest")
val currentRisk = rsb.join(latest,
    $"rsb.pair" === $"latest.pair" && $"rsb.project" === $"latest.project" && $"rsb.window_start_ts" === $"latest.max_ts")
  .select($"rsb.pair", $"rsb.project", $"rsb.baseline_status", $"rsb.risk_score", $"rsb.dt", $"rsb.window_start_ts")
  .orderBy("pair", "project")
writeJson("current_risk.json", arrayJson(currentRisk.toJSON.collect()))

// 2. USDC crisis timeline: USDC_USDT / curve, the pair this project's
// backfill was originally validated against (ARCHITECTURE.md).
val usdcTimeline = spark.table("meridian.stablecoin_pool_hourly")
  .filter($"pair" === "USDC_USDT" && $"project" === "curve" &&
          $"dt" >= "2023-03-08" && $"dt" <= "2023-03-15" && $"is_valid_price" === true)
  .select($"window_start_ts", $"implied_price", $"volume_usd")
  .orderBy("window_start_ts")
writeJson("usdc_crisis_timeline.json", arrayJson(usdcTimeline.toJSON.collect()))

// 3. UST crisis timeline: UST_USDC / curve.
val ustTimeline = spark.table("meridian.stablecoin_pool_hourly")
  .filter($"pair" === "UST_USDC" && $"project" === "curve" &&
          $"dt" >= "2022-05-07" && $"dt" <= "2022-05-16" && $"is_valid_price" === true)
  .select($"window_start_ts", $"implied_price", $"volume_usd")
  .orderBy("window_start_ts")
writeJson("ust_crisis_timeline.json", arrayJson(ustTimeline.toJSON.collect()))

// 4. Classifier metrics: all 6 rows (2 directions x 3 scorers).
val metrics = spark.table("meridian.crisis_classifier_metrics")
  .select("direction", "scorer", "n_test", "n_test_crisis", "precision_crisis", "recall_crisis", "f1_crisis", "pr_auc", "threshold_used")
  .orderBy("direction", "scorer")
writeJson("classifier_metrics.json", arrayJson(metrics.toJSON.collect()))

// 5. Top wallet PageRank entries for both crisis windows, with contract
// labels joined in — the point is surfacing the contract-vs-EOA finding,
// not just a bare ranking.
val wp = spark.table("meridian.wallet_pagerank").filter($"node_type" === "WALLET" && $"rank_within_window" <= 10)
val wl = spark.table("meridian.wallet_labels")
val wallets = wp.filter($"window_label".isin("USDC_MAR2023_CRISIS", "UST_MAY2022_CRISIS"))
  .join(wl, wp("node_id") === wl("address"), "left")
  .select(wp("window_label"), wp("node_id"), wp("pagerank_score"), wp("rank_within_window"),
          coalesce(wl("is_contract"), lit(false)).as("is_contract"), wl("label"))
  .orderBy("window_label", "rank_within_window")
writeJson("wallet_rankings.json", arrayJson(wallets.toJSON.collect()))

// 6. Metadata: when this export ran and what the underlying dataset covers
// — feeds the "historical replay, not live" framing on the dashboard.
val meta = s"""{"exported_at":"${Instant.now()}","dataset_end_usdc":"2023-05-31","dataset_end_ust":"2022-06-15","usdc_crisis_window":["2023-03-08","2023-03-15"],"ust_crisis_window":["2022-05-07","2022-05-16"]}"""
writeJson("metadata.json", meta)

println("\nExport complete.")
System.exit(0)
