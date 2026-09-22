// Computes the lead-time / false-alarm evaluation for the two documented
// crisis events, writing dashboard/data/evaluation_summary.json. Design
// and full methodology confirmed with the user before writing this and
// validated first as a standalone analysis before being ported here (see
// docs/FINDINGS.md's "Does the risk score provide genuine early warning,
// not just after-the-fact detection?" section for the full writeup) — not
// written speculatively.
//
// Deliberately NOT part of export_dashboard_data.scala's batch: this
// analyzes two fixed historical events, not live/evolving pipeline
// output, so it belongs in its own script, same "run manually, re-run
// only if the methodology or underlying data changes" model as
// spark/baseline_crisis_stats.scala. Each event's series (a few thousand
// rows at most) is collected to the driver — Spark DataFrames aren't a
// good fit for the sequential, stateful episode-finding logic below, and
// this data volume makes collecting it a non-issue.

import org.apache.spark.sql.SparkSession
import java.io.PrintWriter
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

val spark = SparkSession.builder.appName("EvaluationSummary").enableHiveSupport().getOrCreate()

val OUT_DIR = "/home/chirag/Desktop/Meridian/dashboard/data"

case class SeriesRow(ts: LocalDateTime, baselineStatus: String, riskScore: Double, price: Option[Double])

case class EvalSummary(
  event_label: String,
  crisis_start: String,
  crisis_end: String,
  threshold_basis: String,
  calm_mean: Option[Double],
  calm_stdev: Option[Double],
  calm_n: Option[Long],
  elevated_threshold: Double,
  depeg_onset_ts: Option[String],
  first_warning_ts: Option[String],
  lead_time_hours: Double,
  false_alarm_count: Int,
  peak_score: Double,
  min_score_during_crisis: Double,
  crisis_hours_total: Int,
  crisis_hours_below_threshold: Int,
  recovery_detected: Boolean,
  recovery_ts: Option[String],
  recovery_delay_hours: Option[Double],
  recovery_na_permanent_collapse: Boolean,
  depeg_magnitude_pct: Double,
  min_price: Double,
  calm_avg_volume_usd: Double,
  crisis_avg_volume_usd: Double,
  calm_caveat: Option[String]
)

def loadSeries(pair: String, project: String): Array[SeriesRow] = {
  val df = spark.sql(s"""
    SELECT r.window_start_ts, r.baseline_status, r.risk_score, p.implied_price
    FROM meridian.risk_scores_baseline r
    JOIN meridian.stablecoin_pool_hourly p
      ON r.pair = p.pair AND r.project = p.project AND r.window_start_ts = p.window_start_ts
    WHERE r.pair = '$pair' AND r.project = '$project' AND p.source = 'dune'
    ORDER BY r.window_start_ts
  """)
  df.collect().map { row =>
    SeriesRow(
      row.getAs[java.sql.Timestamp]("window_start_ts").toLocalDateTime,
      row.getAs[String]("baseline_status"),
      row.getAs[Double]("risk_score"),
      if (row.isNullAt(row.fieldIndex("implied_price"))) None else Some(row.getAs[Double]("implied_price"))
    )
  }
}

def mean(xs: Seq[Double]): Double = xs.sum / xs.length
def stdev(xs: Seq[Double]): Double = {
  val m = mean(xs)
  math.sqrt(xs.map(x => math.pow(x - m, 2)).sum / (xs.length - 1))
}

// Contiguous runs of >= threshold, each >= minLen hours long. Returns
// (startIdx, endIdx) inclusive pairs.
def findEpisodes(rows: Array[SeriesRow], threshold: Double, minLen: Int = 2): Array[(Int, Int)] = {
  val episodes = scala.collection.mutable.ArrayBuffer[(Int, Int)]()
  var i = 0
  val n = rows.length
  while (i < n) {
    if (rows(i).riskScore >= threshold) {
      var j = i
      while (j < n && rows(j).riskScore >= threshold) j += 1
      if ((j - i) >= minLen) episodes += ((i, j - 1))
      i = j
    } else i += 1
  }
  episodes.toArray
}

def hoursBetween(a: LocalDateTime, b: LocalDateTime): Double =
  java.time.Duration.between(a, b).toMinutes / 60.0

def analyze(
  eventLabel: String, rows: Array[SeriesRow], crisisStart: String, crisisEnd: String,
  depegThreshold: Double, recovers: Boolean, fixedThreshold: Option[Double],
  depegMagnitudePct: Double, minPrice: Double, calmAvgVolume: Double, crisisAvgVolume: Double,
  calmCaveat: Option[String]
): (EvalSummary, Double) = {
  val fmt = DateTimeFormatter.ISO_LOCAL_DATE
  val crisisStartDt = LocalDateTime.parse(crisisStart + "T00:00:00")
  val crisisEndDt = LocalDateTime.parse(crisisEnd + "T00:00:00")

  val (threshold, thresholdBasis, calmMean, calmStd, calmN) = fixedThreshold match {
    case Some(t) => (t, "cross_pair_from_usdc", None, None, None)
    case None =>
      // Only RELIABLE rows count as genuine calm -- NO_RELIABLE_BASELINE
      // rows are excluded deliberately: that status means exactly what it
      // says (see docs/FINDINGS.md's no-reliable-baseline finding), so
      // including them would make the "calm" reference circular.
      val calmRows = rows.filter(r => r.baselineStatus == "RELIABLE" &&
        !(!r.ts.isBefore(crisisStartDt) && !r.ts.isAfter(crisisEndDt)))
      val calmScores = calmRows.map(_.riskScore).toSeq
      val m = mean(calmScores)
      val s = stdev(calmScores)
      (m + 2 * s, "self", Some(m), Some(s), Some(calmScores.length.toLong))
  }

  // Sustained (>=2h) price-based depeg onset, searched from 30 days
  // before crisis start through crisis end -- a single-hour price spike
  // (confirmed happening in the real data: implied_price=$1.1666 on
  // 2023-03-08, is_valid_price=true, anomaly_flag=NONE, a thin-trade
  // artifact) would otherwise be mistaken for onset.
  val searchStart = crisisStartDt.minusDays(30)
  var onsetIdx: Option[Int] = None
  var i = 0
  val n = rows.length
  while (i < n && onsetIdx.isEmpty) {
    val r = rows(i)
    val inRange = !r.ts.isBefore(searchStart) && !r.ts.isAfter(crisisEndDt)
    val deviates = r.price.isEmpty || math.abs(r.price.get - 1.0) >= depegThreshold
    if (inRange && deviates) {
      var j = i
      while (j < n && !rows(j).ts.isAfter(crisisEndDt) &&
             (rows(j).price.isEmpty || math.abs(rows(j).price.get - 1.0) >= depegThreshold)) j += 1
      if ((j - i) >= 2) onsetIdx = Some(i)
      i = if (j > i) j else i + 1
    } else i += 1
  }
  val onset = onsetIdx.map(rows(_))

  val episodes = findEpisodes(rows, threshold, 2)
  var trueSignalIdx: Option[Int] = None
  val falseAlarms = scala.collection.mutable.ArrayBuffer[(Int, Int)]()
  episodes.foreach { case (ei, ej) =>
    val startTs = rows(ei).ts
    val inLeadWindow = onset.isDefined && !startTs.isBefore(searchStart) &&
      !startTs.isAfter(crisisEndDt) && !startTs.isAfter(onset.get.ts)
    if (inLeadWindow) {
      if (trueSignalIdx.isEmpty || startTs.isAfter(rows(trueSignalIdx.get).ts)) trueSignalIdx = Some(ei)
    } else if (!(!startTs.isBefore(crisisStartDt) && !startTs.isAfter(crisisEndDt))) {
      falseAlarms += ((ei, ej))
    }
  }

  val (firstWarningTs, leadTimeHours) = (trueSignalIdx, onset) match {
    case (Some(idx), Some(o)) => (Some(rows(idx).ts), hoursBetween(rows(idx).ts, o.ts))
    case _ => (None, 0.0)
  }

  val crisisRows = rows.filter(r => !r.ts.isBefore(crisisStartDt) && !r.ts.isAfter(crisisEndDt))
  val peakScore = crisisRows.map(_.riskScore).max
  val minScoreDuringCrisis = crisisRows.map(_.riskScore).min
  val belowThresholdHours = crisisRows.count(_.riskScore < threshold)

  val (recoveryDetected, recoveryTs, recoveryDelay) = if (recovers) {
    val post = rows.filter(_.ts.isAfter(crisisEndDt))
    post.find(r => r.riskScore < threshold && r.price.isDefined && math.abs(r.price.get - 1.0) < depegThreshold) match {
      case Some(r) => (true, Some(r.ts), Some(hoursBetween(crisisEndDt, r.ts)))
      case None => (false, None, None)
    }
  } else (false, None, None)

  // Hive's TIMESTAMP columns are timezone-naive but documented throughout
  // this project as always representing UTC (see e.g. hive/schema.sql's
  // "Start of the hourly aggregation window (UTC)"). Appending "Z"
  // explicitly here, rather than relying on Postgres's session timezone
  // default to interpret a bare string correctly on insert, removes any
  // ambiguity before it can reach the frontend.
  val isoFmt = DateTimeFormatter.ISO_LOCAL_DATE_TIME
  def isoUtc(dt: LocalDateTime): String = dt.format(isoFmt) + "Z"
  val summary = EvalSummary(
    event_label = eventLabel,
    crisis_start = crisisStart,
    crisis_end = crisisEnd,
    threshold_basis = thresholdBasis,
    calm_mean = calmMean.map(v => math.round(v * 100) / 100.0),
    calm_stdev = calmStd.map(v => math.round(v * 100) / 100.0),
    calm_n = calmN,
    elevated_threshold = math.round(threshold * 100) / 100.0,
    depeg_onset_ts = onset.map(r => isoUtc(r.ts)),
    first_warning_ts = firstWarningTs.map(isoUtc),
    lead_time_hours = math.round(leadTimeHours * 10) / 10.0,
    false_alarm_count = falseAlarms.length,
    peak_score = math.round(peakScore * 100) / 100.0,
    min_score_during_crisis = math.round(minScoreDuringCrisis * 100) / 100.0,
    crisis_hours_total = crisisRows.length,
    crisis_hours_below_threshold = belowThresholdHours,
    recovery_detected = recoveryDetected,
    recovery_ts = recoveryTs.map(isoUtc),
    recovery_delay_hours = recoveryDelay.map(v => math.round(v * 10) / 10.0),
    recovery_na_permanent_collapse = !recovers,
    depeg_magnitude_pct = depegMagnitudePct,
    min_price = minPrice,
    calm_avg_volume_usd = calmAvgVolume,
    crisis_avg_volume_usd = crisisAvgVolume,
    calm_caveat = calmCaveat
  )
  (summary, threshold)
}

val usdcSeries = loadSeries("USDC_USDT", "curve")
val ustSeries = loadSeries("UST_USDC", "curve")

println(s"USDC series: ${usdcSeries.length} rows (${usdcSeries.head.ts} to ${usdcSeries.last.ts})")
println(s"UST series: ${ustSeries.length} rows (${ustSeries.head.ts} to ${ustSeries.last.ts})")

val (usdcSummary, usdcThreshold) = analyze(
  "USDC_MAR2023", usdcSeries, "2023-03-08", "2023-03-15", 0.01, recovers = true, fixedThreshold = None,
  depegMagnitudePct = 11.92, minPrice = 0.8808,
  calmAvgVolume = 3390884.22, crisisAvgVolume = 31375592.0, calmCaveat = None
)

val (ustSummary, _) = analyze(
  "UST_MAY2022", ustSeries, "2022-05-07", "2022-05-16", 0.01, recovers = false, fixedThreshold = Some(usdcThreshold),
  depegMagnitudePct = 96.66, minPrice = 0.0334,
  calmAvgVolume = 448430.16, crisisAvgVolume = 1089286.0,
  calmCaveat = Some("No genuine RELIABLE (calm) rows exist for UST in this dataset -- this is the " +
    "pre-crisis-window average, not a validated calm baseline.")
)

// Hand-built JSON, not Seq(...).toDS().toJSON.collect() -- routing just 2
// rows through Spark's distributed job machinery for the final write
// isn't just overkill, it's fragile: confirmed hanging in practice,
// stuck waiting on executor threads starved by the concurrently-running
// meridian-stream-consumer.service (a real, separate long-running Spark
// job on this same machine), even though all the actual computation
// above (collected to the driver, no distributed execution needed) had
// already finished. export_dashboard_data.scala's own metadata.json
// already hand-builds its JSON the same way, for the same reason: a
// small, fixed-shape object doesn't need a Spark job.
def jsonStr(s: String): String = "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
def jsonOpt(o: Option[String]): String = o.map(jsonStr).getOrElse("null")
def jsonOptD(o: Option[Double]): String = o.map(_.toString).getOrElse("null")
def jsonOptL(o: Option[Long]): String = o.map(_.toString).getOrElse("null")

def toJson(s: EvalSummary): String =
  s"""{"event_label":${jsonStr(s.event_label)},"crisis_start":${jsonStr(s.crisis_start)},""" +
  s""""crisis_end":${jsonStr(s.crisis_end)},"threshold_basis":${jsonStr(s.threshold_basis)},""" +
  s""""calm_mean":${jsonOptD(s.calm_mean)},"calm_stdev":${jsonOptD(s.calm_stdev)},"calm_n":${jsonOptL(s.calm_n)},""" +
  s""""elevated_threshold":${s.elevated_threshold},"depeg_onset_ts":${jsonOpt(s.depeg_onset_ts)},""" +
  s""""first_warning_ts":${jsonOpt(s.first_warning_ts)},"lead_time_hours":${s.lead_time_hours},""" +
  s""""false_alarm_count":${s.false_alarm_count},"peak_score":${s.peak_score},""" +
  s""""min_score_during_crisis":${s.min_score_during_crisis},"crisis_hours_total":${s.crisis_hours_total},""" +
  s""""crisis_hours_below_threshold":${s.crisis_hours_below_threshold},"recovery_detected":${s.recovery_detected},""" +
  s""""recovery_ts":${jsonOpt(s.recovery_ts)},"recovery_delay_hours":${jsonOptD(s.recovery_delay_hours)},""" +
  s""""recovery_na_permanent_collapse":${s.recovery_na_permanent_collapse},""" +
  s""""depeg_magnitude_pct":${s.depeg_magnitude_pct},"min_price":${s.min_price},""" +
  s""""calm_avg_volume_usd":${s.calm_avg_volume_usd},"crisis_avg_volume_usd":${s.crisis_avg_volume_usd},""" +
  s""""calm_caveat":${jsonOpt(s.calm_caveat)}}"""

val pw = new PrintWriter(s"$OUT_DIR/evaluation_summary.json")
pw.write(Seq(usdcSummary, ustSummary).map(toJson).mkString("[", ",", "]"))
pw.close()
println(s"Wrote $OUT_DIR/evaluation_summary.json")

println("\n=== USDC ===")
println(usdcSummary)
println("\n=== UST ===")
println(ustSummary)

System.exit(0)
