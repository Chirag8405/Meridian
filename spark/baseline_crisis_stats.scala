// Computes baseline (calm-market) and crisis-window statistics per
// (pair, project) for Meridian's risk model, writing results to
// meridian.baseline_stats and meridian.crisis_stats (see
// hive/baseline_crisis_stats_schema.sql for the tables and the design
// decisions behind them — not partitioned, grouped by pair+project not
// just pair).
//
// Run via spark-shell -i (not spark-submit, to match how the rest of this
// project's Spark verification has been run). Launch via nohup, not
// directly — see CLAUDE.md's conventions section for why.

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._

val spark = SparkSession.builder.appName("BaselineCrisisStats").enableHiveSupport().getOrCreate()
import spark.implicits._

val df = spark.table("meridian.stablecoin_pool_hourly")

// Crisis windows (inclusive on both ends)
val usdcCrisisStart = "2023-03-08"
val usdcCrisisEnd   = "2023-03-15"
val ustCrisisStart  = "2022-05-07"
val ustCrisisEnd    = "2022-05-16"

val SMALL_SAMPLE_THRESHOLD = 30

def statsAgg: Seq[org.apache.spark.sql.Column] = Seq(
  count(when($"is_valid_price" === true, 1)).as("n_price_rows"),
  count(lit(1)).as("n_total_rows"),
  avg(when($"is_valid_price" === true, $"implied_price")).as("mean_price"),
  stddev(when($"is_valid_price" === true, $"implied_price")).as("stddev_price"),
  expr("percentile(CASE WHEN is_valid_price THEN implied_price END, 0.1)").as("p10_price"),
  expr("percentile(CASE WHEN is_valid_price THEN implied_price END, 0.25)").as("p25_price"),
  expr("percentile(CASE WHEN is_valid_price THEN implied_price END, 0.75)").as("p75_price"),
  expr("percentile(CASE WHEN is_valid_price THEN implied_price END, 0.9)").as("p90_price"),
  avg($"volume_usd").as("mean_volume_usd"),
  stddev($"volume_usd").as("stddev_volume_usd"),
  avg($"trade_count".cast("double")).as("mean_trade_count"),
  stddev($"trade_count".cast("double")).as("stddev_trade_count")
)

// --- Baseline: exclude BOTH crisis windows ---
val baselineDf = df.filter(
  !($"dt" >= usdcCrisisStart && $"dt" <= usdcCrisisEnd) &&
  !($"dt" >= ustCrisisStart && $"dt" <= ustCrisisEnd)
)

// baseline_status / baseline_status_note: distinct from small_sample_flag.
// All three UST pairs clear n>=30 but have no genuine calm period anywhere
// in the dataset's time range (2022-04-15 to 2022-06-15) — see docs/FINDINGS.md
// for the full analysis. Sub-period numbers below were computed directly
// against meridian.stablecoin_pool_hourly, split at the crisis window
// boundaries (pre: before 2022-05-07, post: after 2022-05-16).
val ustNotes = Map(
  "UST_USDC" -> "No genuine calm period in dataset (2022-04-15 to 2022-06-15). Pre-crisis-window sub-period (2022-04-15 to 2022-05-06): n=157, mean=$0.769, stddev=0.250 (already unstable, well before the 2022-05-07 crisis boundary). Post-crisis-window sub-period (2022-05-17 to 2022-06-15): n=66, mean=$0.047, stddev=0.031 (collapsed, not recovered). See docs/FINDINGS.md.",
  "UST_USDT" -> "No genuine calm period in dataset (2022-04-15 to 2022-06-15). Pre-crisis-window sub-period (2022-04-15 to 2022-05-06): n=48, mean=$0.808, stddev=0.312 (already unstable, well before the 2022-05-07 crisis boundary). Post-crisis-window sub-period (2022-05-17 to 2022-06-15): n=11, mean=$0.044, stddev=0.035 (collapsed, not recovered). See docs/FINDINGS.md.",
  "UST_DAI" -> "No genuine calm period in dataset (2022-04-15 to 2022-06-15). Pre-crisis-window sub-period (2022-04-15 to 2022-05-06): n=64, mean=$1.0016, stddev=0.0018 (looks calm in isolation, but low volume and immediately followed by total collapse — not a reliable standalone baseline). Post-crisis-window sub-period (2022-05-17 to 2022-06-15): n=28, mean=$0.035, stddev=0.027 (collapsed, not recovered). See docs/FINDINGS.md."
)

val baselineAggCols = statsAgg
val baselineStats = baselineDf.groupBy($"pair", $"project")
  .agg(baselineAggCols.head, baselineAggCols.tail: _*)
  .withColumn("small_sample_flag", $"n_price_rows" < SMALL_SAMPLE_THRESHOLD)
  .withColumn("baseline_status", when($"pair".isin("UST_USDC", "UST_USDT", "UST_DAI"), lit("NO_RELIABLE_BASELINE")).otherwise(lit("RELIABLE")))
  .withColumn("baseline_status_note",
    when($"pair" === "UST_USDC", lit(ustNotes("UST_USDC")))
      .when($"pair" === "UST_USDT", lit(ustNotes("UST_USDT")))
      .when($"pair" === "UST_DAI", lit(ustNotes("UST_DAI")))
      .otherwise(lit(null: String)))
  .withColumn("computed_at", current_timestamp())

baselineStats.createOrReplaceTempView("baseline_stats_computed")
spark.sql("""
  INSERT INTO TABLE meridian.baseline_stats
  SELECT pair, project, n_price_rows, n_total_rows, mean_price, stddev_price,
         p10_price, p25_price, p75_price, p90_price,
         mean_volume_usd, stddev_volume_usd, mean_trade_count, stddev_trade_count,
         small_sample_flag, baseline_status, baseline_status_note, computed_at
  FROM baseline_stats_computed
""")

// --- Crisis: each window computed separately, only for pairs with data in it ---
val usdcCrisisDf = df.filter($"dt" >= usdcCrisisStart && $"dt" <= usdcCrisisEnd)
  .withColumn("crisis_window", lit("USDC_MAR2023"))
  .withColumn("crisis_start_dt", lit(usdcCrisisStart))
  .withColumn("crisis_end_dt", lit(usdcCrisisEnd))

val ustCrisisDf = df.filter($"dt" >= ustCrisisStart && $"dt" <= ustCrisisEnd)
  .withColumn("crisis_window", lit("UST_MAY2022"))
  .withColumn("crisis_start_dt", lit(ustCrisisStart))
  .withColumn("crisis_end_dt", lit(ustCrisisEnd))

val crisisDf = usdcCrisisDf.unionByName(ustCrisisDf)

val crisisAggCols = statsAgg
val crisisStats = crisisDf.groupBy($"pair", $"project", $"crisis_window", $"crisis_start_dt", $"crisis_end_dt")
  .agg(crisisAggCols.head, crisisAggCols.tail: _*)
  .withColumn("small_sample_flag", $"n_price_rows" < SMALL_SAMPLE_THRESHOLD)
  .withColumn("computed_at", current_timestamp())

crisisStats.createOrReplaceTempView("crisis_stats_computed")
spark.sql("""
  INSERT INTO TABLE meridian.crisis_stats
  SELECT pair, project, crisis_window, crisis_start_dt, crisis_end_dt,
         n_price_rows, n_total_rows, mean_price, stddev_price,
         p10_price, p25_price, p75_price, p90_price,
         mean_volume_usd, stddev_volume_usd, mean_trade_count, stddev_trade_count,
         small_sample_flag, computed_at
  FROM crisis_stats_computed
""")

println("=== BASELINE STATS (all pairs/projects) ===")
spark.sql("SELECT pair, project, n_price_rows, small_sample_flag, baseline_status, mean_price, stddev_price, p10_price, p90_price FROM meridian.baseline_stats ORDER BY pair, project").show(50, false)

println("=== CRISIS STATS (all pairs/projects/windows) ===")
spark.sql("SELECT pair, project, crisis_window, n_price_rows, small_sample_flag, mean_price, stddev_price, p10_price, p90_price FROM meridian.crisis_stats ORDER BY crisis_window, pair, project").show(50, false)

println("=== SMALL SAMPLE FLAGS ===")
spark.sql("SELECT pair, project, n_price_rows, 'baseline' AS source FROM meridian.baseline_stats WHERE small_sample_flag = true UNION ALL SELECT pair, project, n_price_rows, concat('crisis:', crisis_window) FROM meridian.crisis_stats WHERE small_sample_flag = true").show(50, false)

System.exit(0)
