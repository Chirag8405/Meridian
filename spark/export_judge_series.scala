// Exports the two historical hourly series the LLM-judge experiment (Part C of
// docs/GENAI_ASSISTANT_PLAN.md) needs: raw behaviour features AND the rule-based
// score for every hour, for USDC_USDT/curve and UST_USDC/curve. Read-only against
// Hive; writes genai/eval/judge/series_*.json. Same series and source filter as
// spark/evaluation_summary.scala (source = 'dune', i.e. historical, never live).
//
// Run (long: starts a Spark session against Hive, so launch detached, per CLAUDE.md):
//   source /home/chirag/bigdata/env.sh
//   nohup $SPARK_HOME/bin/spark-shell -i spark/export_judge_series.scala > /tmp/judge_export.log 2>&1 &
//
// Hand-built JSON on purpose, for the same reason as evaluation_summary.scala: small
// collected result, and routing it through a distributed write hung before when the
// streaming consumer was starving executors.

import org.apache.spark.sql.SparkSession
import java.io.PrintWriter
import java.time.format.DateTimeFormatter

val spark = SparkSession.builder.appName("ExportJudgeSeries").enableHiveSupport().getOrCreate()
val OUT_DIR = "/home/chirag/Desktop/Meridian/genai/eval/judge"
val isoFmt = DateTimeFormatter.ISO_LOCAL_DATE_TIME

def num(v: Any): String = v match {
  case null => "null"
  case d: java.lang.Double => if (d.isNaN || d.isInfinite) "null" else d.toString
  case l: java.lang.Long => l.toString
  case i: java.lang.Integer => i.toString
  case other => other.toString
}

def export(pair: String, project: String, file: String): Unit = {
  val rows = spark.sql(s"""
    SELECT p.window_start_ts, p.implied_price, p.volume_usd, p.trade_count, p.is_valid_price,
           p.anomaly_flag, r.baseline_status, r.risk_score,
           r.price_severity, r.volume_trade_severity, r.cluster_severity, r.wallet_concentration_severity
    FROM meridian.stablecoin_pool_hourly p
    JOIN meridian.risk_scores_baseline r
      ON r.pair = p.pair AND r.project = p.project AND r.window_start_ts = p.window_start_ts
    WHERE p.pair = '$pair' AND p.project = '$project' AND p.source = 'dune'
    ORDER BY p.window_start_ts
  """).collect()
  val body = rows.map { r =>
    val ts = r.getAs[java.sql.Timestamp]("window_start_ts").toLocalDateTime.format(isoFmt) + "Z"
    def col(n: String): String = num(r.getAs[Any](n))
    val flag = Option(r.getAs[String]("anomaly_flag")).map(s => "\"" + s + "\"").getOrElse("null")
    val valid = Option(r.getAs[java.lang.Boolean]("is_valid_price")).map(_.toString).getOrElse("null")
    s"""{"ts":"$ts","implied_price":${col("implied_price")},"volume_usd":${col("volume_usd")},""" +
    s""""trade_count":${col("trade_count")},"is_valid_price":$valid,"anomaly_flag":$flag,""" +
    s""""baseline_status":"${r.getAs[String]("baseline_status")}","risk_score":${col("risk_score")}}"""
  }
  val pw = new PrintWriter(s"$OUT_DIR/$file")
  pw.write(s"""{"pair":"$pair","project":"$project","rows":[""" + body.mkString(",") + "]}")
  pw.close()
  println(s"Wrote $OUT_DIR/$file: ${rows.length} rows")
}

export("USDC_USDT", "curve", "series_usdc.json")
export("UST_USDC", "curve", "series_ust.json")
println("Export complete.")
System.exit(0)
