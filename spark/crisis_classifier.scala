// Trains and evaluates the ML crisis classifier, comparing it against the
// rule-based baseline (meridian.risk_scores_baseline) on identical held-out
// test rows. Design decided and confirmed with the user before writing this
// (see docs/FINDINGS.md for the full report: label grounding, feature
// exclusions, the leave-one-coin-out split and its Direction-2 asymmetry) —
// not written speculatively.
//
// Two LOCO directions:
//   TEST_ON_UST   — pure single-coin LOCO. Train on USDC (calm minus a
//                    chronological holdout, + USDC's own crisis rows).
//                    Test on the USDC calm holdout + all of UST.
//   TEST_ON_USDC  — necessarily coin-blended for the CALM class, since UST
//                    has none. Train on USDC calm (same holdout) + all of
//                    UST (CRISIS). Test on the USDC calm holdout + USDC's
//                    own crisis rows (held out entirely, unseen).
//
// Two model types per direction: logistic regression, random forest — both
// class-weighted (inverse frequency, computed per training fold).

import org.apache.spark.sql.{SparkSession, DataFrame}
import org.apache.spark.sql.functions._
import org.apache.spark.ml.feature.VectorAssembler
import org.apache.spark.ml.classification.{LogisticRegression, RandomForestClassifier}
import org.apache.spark.ml.evaluation.BinaryClassificationEvaluator
import org.apache.spark.ml.linalg.Vector

val spark = SparkSession.builder.appName("CrisisClassifier").enableHiveSupport().getOrCreate()
import spark.implicits._

val HOLDOUT_CUTOFF = "2023-05-01"

val cf = spark.table("meridian.crisis_features")
val rsb = spark.table("meridian.risk_scores_baseline").select("pair", "project", "window_start_ts", "risk_score")

// Feature assembly: price_severity, volume_trade_severity,
// wallet_concentration_severity, trend/velocity (0-imputed, with an
// explicit availability flag rather than silently treating "unknown" as
// "zero trend"), and cluster_id one-hot (k=4, manually one-hot for
// transparency rather than a StringIndexer/OneHotEncoder pipeline).
// Deliberately EXCLUDES cluster_severity and risk_score (see
// hive/crisis_features_schema.sql notes on leakage).
val withFeatures = cf
  .withColumn("velocity_imputed", coalesce($"price_severity_velocity", lit(0.0)))
  .withColumn("rolling_mean_imputed", coalesce($"price_severity_rolling_mean_3h", $"price_severity"))
  .withColumn("rolling_slope_imputed", coalesce($"price_severity_rolling_slope_3h", lit(0.0)))
  .withColumn("trend_available_num", when($"trend_available", lit(1.0)).otherwise(lit(0.0)))
  .withColumn("is_cluster_0", when($"cluster_id" === 0, lit(1.0)).otherwise(lit(0.0)))
  .withColumn("is_cluster_1", when($"cluster_id" === 1, lit(1.0)).otherwise(lit(0.0)))
  .withColumn("is_cluster_2", when($"cluster_id" === 2, lit(1.0)).otherwise(lit(0.0)))
  .withColumn("is_cluster_3", when($"cluster_id" === 3, lit(1.0)).otherwise(lit(0.0)))

// wallet_concentration_severity was EXCLUDED after the first training run:
// it's a constant broadcast per named window (USDC: exactly 0.1283 calm /
// 0.4339 crisis; UST: exactly 0.0 always), not a per-row-computed value —
// on inspection it behaves as a near-direct label proxy rather than a
// graded severity signal, and dominated Random Forest's feature
// importances (0.53-0.82) in a way that likely reflected that shortcut
// rather than genuine trend-based generalization. See docs/FINDINGS.md.
val featureCols = Array(
  "price_severity", "volume_trade_severity",
  "velocity_imputed", "trend_available_num", "rolling_mean_imputed", "rolling_slope_imputed",
  "is_cluster_0", "is_cluster_1", "is_cluster_2", "is_cluster_3"
)
// Shared F1-maximizing threshold sweep, applied identically to the trained
// models' predicted probabilities and the baseline's risk_score — a fixed
// 0.5 cutoff is not a fair comparison when the baseline gets its own
// optimized threshold; both need the same treatment.
def bestThresholdF1(pairs: Array[(Int, Double)], thresholds: Seq[Double]): (Double, Double, Double, Double) = {
  var bestF1 = -1.0; var bestThresh = thresholds.head; var bestP = 0.0; var bestR = 0.0
  for (t <- thresholds) {
    var tp = 0; var fp = 0; var fn = 0
    for ((label, score) <- pairs) {
      if (label == 1 && score >= t) tp += 1
      else if (label == 0 && score >= t) fp += 1
      else if (label == 1 && score < t) fn += 1
    }
    val p = if (tp + fp == 0) 0.0 else tp.toDouble / (tp + fp)
    val r = if (tp + fn == 0) 0.0 else tp.toDouble / (tp + fn)
    val f1 = if (p + r == 0) 0.0 else 2 * p * r / (p + r)
    if (f1 > bestF1) { bestF1 = f1; bestThresh = t; bestP = p; bestR = r }
  }
  (bestThresh, bestP, bestR, bestF1)
}

val assembler = new VectorAssembler().setInputCols(featureCols).setOutputCol("features")
val assembled = assembler.transform(withFeatures).join(rsb, Seq("pair", "project", "window_start_ts"))

val usdcCalm = assembled.filter($"baseline_status" === "RELIABLE" && $"label" === 0)
val usdcCrisis = assembled.filter($"baseline_status" === "RELIABLE" && $"label" === 1)
val ustAll = assembled.filter($"baseline_status" === "NO_RELIABLE_BASELINE") // 100% label=1

val usdcCalmTrainPool = usdcCalm.filter($"dt" < HOLDOUT_CUTOFF)
val usdcCalmHoldout = usdcCalm.filter($"dt" >= HOLDOUT_CUTOFF)

def withClassWeight(df: DataFrame): DataFrame = {
  val counts = df.groupBy("label").count().collect().map(r => r.getInt(0) -> r.getLong(1)).toMap
  val total = counts.values.sum.toDouble
  val nClasses = counts.size.toDouble
  val weightUdf = udf((label: Int) => total / (nClasses * counts(label)))
  df.withColumn("classWeight", weightUdf($"label"))
}

val trainDir1 = withClassWeight(usdcCalmTrainPool.unionByName(usdcCrisis))
val testDir1 = usdcCalmHoldout.unionByName(ustAll)

val trainDir2 = withClassWeight(usdcCalmTrainPool.unionByName(ustAll))
val testDir2 = usdcCalmHoldout.unionByName(usdcCrisis)

println(s"Direction TEST_ON_UST:  train=${trainDir1.count()} (calm=${usdcCalmTrainPool.count()}, crisis=${usdcCrisis.count()}), test=${testDir1.count()} (holdout_calm=${usdcCalmHoldout.count()}, ust=${ustAll.count()})")
println(s"Direction TEST_ON_USDC: train=${trainDir2.count()} (calm=${usdcCalmTrainPool.count()}, ust_crisis=${ustAll.count()}), test=${testDir2.count()} (holdout_calm=${usdcCalmHoldout.count()}, usdc_crisis=${usdcCrisis.count()})")

def trainAndEval(direction: String, train: DataFrame, test: DataFrame): Unit = {
  val lr = new LogisticRegression().setFeaturesCol("features").setLabelCol("label").setWeightCol("classWeight")
  val rf = new RandomForestClassifier().setFeaturesCol("features").setLabelCol("label").setWeightCol("classWeight").setSeed(42L)

  val lrModel = lr.fit(train)
  val rfModel = rf.fit(train)
  val models = Seq(("logistic_regression", lrModel), ("random_forest", rfModel))

  println(s"\n[$direction] Random Forest feature importances:")
  featureCols.zip(rfModel.featureImportances.toArray).sortBy(-_._2).foreach { case (name, imp) =>
    println(f"  $name%-35s $imp%.4f")
  }
  println(s"\n[$direction] Logistic Regression coefficients:")
  featureCols.zip(lrModel.coefficients.toArray).sortBy(-_._2.abs).foreach { case (name, coef) =>
    println(f"  $name%-35s $coef%+.4f")
  }

  val probToDouble = udf((v: Vector) => v(1))

  var allPreds = Seq[DataFrame]()
  var allMetrics = Seq[(String, String, Long, Long, Long, Double, Double, Double, Double, Double)]()

  for ((modelName, model) <- models) {
    val preds = model.transform(test)
      .withColumn("predicted_prob", probToDouble($"probability"))
      .withColumn("predicted_label", $"prediction".cast("int"))

    val predsOut = preds.select(
      lit(direction).as("direction"), lit(modelName).as("model_type"),
      $"pair", $"project", $"window_start_ts", $"dt",
      $"label".as("true_label"), $"predicted_prob", $"predicted_label", $"risk_score".as("baseline_risk_score")
    ).withColumn("computed_at", current_timestamp())
    allPreds = allPreds :+ predsOut

    val evaluator = new BinaryClassificationEvaluator()
      .setLabelCol("label").setRawPredictionCol("predicted_prob").setMetricName("areaUnderPR")
    val prAuc = evaluator.evaluate(preds)

    val modelPairs = preds.select($"label", $"predicted_prob").collect().map(r => (r.getInt(0), r.getDouble(1)))
    val (bestThresh, precision, recall, f1) = bestThresholdF1(modelPairs, (0 to 100).map(_ / 100.0))

    val nCrisis = test.filter($"label" === 1).count()
    val nCalm = test.filter($"label" === 0).count()
    allMetrics = allMetrics :+ (direction, modelName, test.count(), nCrisis, nCalm, precision, recall, f1, prAuc, bestThresh)

    println(f"[$direction / $modelName] n_test=${test.count()} best_thresh=$bestThresh%.2f precision=$precision%.3f recall=$recall%.3f f1=$f1%.3f pr_auc=$prAuc%.3f")
  }

  // Baseline comparison on the SAME test rows: same threshold-sweep
  // methodology as the models above, plus PR-AUC (threshold-independent).
  val baselineEval = new BinaryClassificationEvaluator()
    .setLabelCol("label").setRawPredictionCol("risk_score").setMetricName("areaUnderPR")
  val baselinePrAuc = baselineEval.evaluate(test)

  val labelScorePairs = test.select($"label", $"risk_score").collect().map(r => (r.getInt(0), r.getDouble(1)))
  val (bestThresh, bestP, bestR, bestF1) = bestThresholdF1(labelScorePairs, (0 to 100).map(_.toDouble))
  val nCrisis = test.filter($"label" === 1).count()
  val nCalm = test.filter($"label" === 0).count()
  allMetrics = allMetrics :+ (direction, "rule_based_baseline", test.count(), nCrisis, nCalm, bestP, bestR, bestF1, baselinePrAuc, bestThresh)
  println(f"[$direction / rule_based_baseline] n_test=${test.count()} best_thresh=$bestThresh precision=$bestP%.3f recall=$bestR%.3f f1=$bestF1%.3f pr_auc=$baselinePrAuc%.3f")

  allPreds.reduce(_.unionByName(_)).createOrReplaceTempView(s"preds_$direction")
  spark.sql(s"""
    INSERT INTO TABLE meridian.crisis_classifier_predictions
    SELECT direction, model_type, pair, project, window_start_ts, dt,
           true_label, predicted_prob, predicted_label, baseline_risk_score, computed_at
    FROM preds_$direction
  """)

  val metricsDf = allMetrics.toDF("direction", "scorer", "n_test", "n_test_crisis", "n_test_calm",
    "precision_crisis", "recall_crisis", "f1_crisis", "pr_auc", "threshold_used")
    .withColumn("computed_at", current_timestamp())
  metricsDf.createOrReplaceTempView(s"metrics_$direction")
  spark.sql(s"""
    INSERT INTO TABLE meridian.crisis_classifier_metrics
    SELECT direction, scorer, n_test, n_test_crisis, n_test_calm,
           precision_crisis, recall_crisis, f1_crisis, pr_auc, threshold_used, computed_at
    FROM metrics_$direction
  """)
}

trainAndEval("TEST_ON_UST", trainDir1, testDir1)
trainAndEval("TEST_ON_USDC", trainDir2, testDir2)

println("\n=== FINAL COMPARISON: model vs. rule-based baseline, same test rows ===")
spark.sql("""
  SELECT direction, scorer, n_test, n_test_crisis, precision_crisis, recall_crisis, f1_crisis, pr_auc, threshold_used
  FROM meridian.crisis_classifier_metrics
  ORDER BY direction, scorer
""").show(20, false)

System.exit(0)
