// Bipartite wallet/pool PageRank — nodes = wallets + pools, edges = trade
// volume between a wallet and a pool it traded against.
//
// DESIGN NOTES (flagged, not silently assumed):
//
// 1. Weighted PageRank requires a custom implementation. GraphX's built-in
//    Graph.pageRank() does NOT support edge weights — it normalizes purely
//    by out-degree (each outgoing edge gets equal share of a vertex's
//    rank, regardless of edge weight). Since we specifically want
//    higher-volume wallet-pool relationships to carry more influence, this
//    script implements weighted PageRank manually via GraphX's Pregel API:
//    outgoing edge weights are normalized to transition probabilities per
//    source vertex, then rank propagates proportional to those weights.
//    This is the standard, well-documented pattern for weighted PageRank
//    in GraphX (no external package needed — Pregel is part of GraphX
//    core, avoiding another Maven-resolution dependency).
//
// 2. Edges are BIDIRECTIONAL (wallet->pool AND pool->wallet, both weighted
//    by the same trade volume), not just wallet->pool. A bipartite graph
//    with edges in only one direction is structurally degenerate for
//    PageRank: pools would accumulate all rank as pure sinks (never
//    redistributing it), and wallets would only ever get the uniform
//    teleportation score, never anything from the pools they trade with.
//    Bidirectional edges let rank flow both ways, so a wallet's influence
//    is boosted by trading with important pools and vice versa — this is
//    the standard bipartite PageRank / recommender-graph technique.
//
// 3. Windows computed separately, not just "calm" vs "crisis" globally:
//    USDC-family pools (Curve 3pool, Uniswap USDC/USDT, Uniswap USDC/DAI)
//    and the UST metapool are structurally unrelated networks (no shared
//    wallets forced into comparison) with different crisis dates, so each
//    gets its own calm/crisis pair rather than one blended "crisis" run.
//
// 4. UST_CALM inherits the same caveat as docs/FINDINGS.md: there is no
//    genuine calm period for UST in this dataset (see baseline_stats).
//    The UST_CALM window here means "outside the 2022-05-07/16 crisis
//    window", not "verified calm" — reported with that caveat, not
//    silently presented as a clean comparison point.

import org.apache.spark.sql.SparkSession
import org.apache.spark.sql.functions._
import org.apache.spark.graphx._
import org.apache.spark.rdd.RDD

val spark = SparkSession.builder.appName("WalletPageRank").enableHiveSupport().getOrCreate()
import spark.implicits._

val trades = spark.table("meridian.wallet_trades_raw")
  .withColumn("amount_usd", coalesce($"amount_usd", lit(0.0)))
  .filter($"taker".isNotNull && $"pool_address".isNotNull)
  .cache()

val CURVE_3POOL = "0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7"
val UNI_USDC_USDT = "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f"
val UNI_USDC_DAI = "0xae461ca67b15dc8dc81ce7615e0320da1a9ab8d5"
val UST_METAPOOL = "0x890f4e345b1daed0367a877a1612f86a1f86985f"

val poolLabels = Map(
  CURVE_3POOL -> "curve_3pool",
  UNI_USDC_USDT -> "uniswap_usdc_usdt",
  UNI_USDC_DAI -> "uniswap_usdc_dai",
  UST_METAPOOL -> "ust_metapool"
)

// --- Global vertex ID mapping (wallets + pools), reused across all windows ---
val distinctWallets = trades.select($"taker".as("addr")).distinct()
val distinctPools = trades.select($"pool_address".as("addr")).distinct()
val allNodes = distinctWallets.union(distinctPools).distinct()
  .rdd.map(_.getString(0)).zipWithUniqueId().cache()

val addrToId: Map[String, Long] = allNodes.collect().toMap
val idToAddr: Map[Long, String] = addrToId.map(_.swap)
val poolAddrSet = Set(CURVE_3POOL, UNI_USDC_USDT, UNI_USDC_DAI, UST_METAPOOL)

def nodeType(addr: String): String = if (poolAddrSet.contains(addr)) "POOL" else "WALLET"

println(s"Total distinct nodes (wallets + pools): ${addrToId.size}")

// --- Weighted PageRank via Pregel (see design note 1 above) ---
def weightedPageRank(edges: RDD[Edge[Double]], numIter: Int = 20, dampingFactor: Double = 0.85): Map[Long, Double] = {
  val vertexIds = edges.flatMap(e => Iterator(e.srcId, e.dstId)).distinct()
  val vertices: RDD[(Long, Double)] = vertexIds.map(id => (id, 1.0))
  val g = Graph(vertices, edges)
  val numVertices = g.vertices.count()
  if (numVertices == 0) return Map.empty[Long, Double]
  val resetProb = 1.0 - dampingFactor
  val teleport = resetProb / numVertices

  val outWeights: VertexRDD[Double] = g.aggregateMessages[Double](
    ctx => ctx.sendToSrc(ctx.attr),
    _ + _
  )
  val gOutW = g.outerJoinVertices(outWeights) { (_, _, wOpt) => wOpt.getOrElse(0.0) }
  val transGraph: Graph[Double, Double] = gOutW
    .mapTriplets(t => if (t.srcAttr > 0) t.attr / t.srcAttr else 0.0)
    .mapVertices((_, _) => 1.0 / numVertices)

  val ranked = transGraph.pregel(0.0, numIter, EdgeDirection.Out)(
    (_, oldRank, msgSum) => teleport + dampingFactor * msgSum,
    triplet => Iterator((triplet.dstId, triplet.srcAttr * triplet.attr)),
    (a, b) => a + b
  )
  ranked.vertices.collect().toMap
}

// Builds bidirectional weighted edges from a filtered trades DataFrame
def buildEdges(filteredTrades: org.apache.spark.sql.DataFrame): RDD[Edge[Double]] = {
  val weighted = filteredTrades.groupBy($"taker", $"pool_address")
    .agg(sum($"amount_usd").as("w"))
    .filter($"w" > 0)
    .collect()
  val edges = weighted.flatMap { row =>
    val wallet = row.getString(0)
    val pool = row.getString(1)
    val w = row.getDouble(2)
    val wid = addrToId(wallet)
    val pid = addrToId(pool)
    Seq(Edge(wid, pid, w), Edge(pid, wid, w))
  }
  spark.sparkContext.parallelize(edges.toSeq)
}

case class WindowDef(windowType: String, windowLabel: String, pools: Set[String], dtFrom: Option[String], dtTo: Option[String], excludeDtFrom: Option[String], excludeDtTo: Option[String])

val windows = Seq(
  WindowDef("OVERALL", "ALL", poolAddrSet, None, None, None, None),
  WindowDef("CALM", "USDC_CALM", Set(CURVE_3POOL, UNI_USDC_USDT, UNI_USDC_DAI), None, None, Some("2023-03-08"), Some("2023-03-15")),
  WindowDef("CRISIS", "USDC_MAR2023_CRISIS", Set(CURVE_3POOL, UNI_USDC_USDT, UNI_USDC_DAI), Some("2023-03-08"), Some("2023-03-15"), None, None),
  WindowDef("CALM", "UST_CALM", Set(UST_METAPOOL), None, None, Some("2022-05-07"), Some("2022-05-16")),
  WindowDef("CRISIS", "UST_MAY2022_CRISIS", Set(UST_METAPOOL), Some("2022-05-07"), Some("2022-05-16"), None, None)
)

var allResults = Seq[(String, String, String, String, Double)]()  // windowType, windowLabel, nodeType, nodeId, score

for (w <- windows) {
  var df = trades.filter($"pool_address".isin(w.pools.toSeq: _*))
  w.dtFrom.foreach(f => df = df.filter($"dt" >= f))
  w.dtTo.foreach(t => df = df.filter($"dt" <= t))
  w.excludeDtFrom.zip(w.excludeDtTo).foreach { case (ef, et) =>
    df = df.filter(!($"dt" >= ef && $"dt" <= et))
  }
  val n = df.count()
  println(s"=== ${w.windowLabel} (${w.windowType}): $n trades ===")

  val edges = buildEdges(df)
  val scores = weightedPageRank(edges)
  val results = scores.toSeq.map { case (id, score) =>
    val addr = idToAddr(id)
    (w.windowType, w.windowLabel, nodeType(addr), addr, score)
  }
  allResults ++= results
}

val resultsDf = allResults.toDF("window_type", "window_label", "node_type", "node_id", "pagerank_score")
  .withColumn("rank_within_window", row_number().over(
    org.apache.spark.sql.expressions.Window
      .partitionBy($"window_label", $"node_type")
      .orderBy($"pagerank_score".desc)
  ))
  .withColumn("computed_at", current_timestamp())

resultsDf.createOrReplaceTempView("wallet_pagerank_computed")
spark.sql("""
  INSERT INTO TABLE meridian.wallet_pagerank
  SELECT window_type, window_label, node_type, node_id, pagerank_score, rank_within_window, computed_at
  FROM wallet_pagerank_computed
""")

println("\n=== TOP 15 OVERALL (ALL window, both node types) ===")
spark.sql("""
  SELECT node_type, node_id, pagerank_score, rank_within_window
  FROM meridian.wallet_pagerank
  WHERE window_label = 'ALL'
  ORDER BY pagerank_score DESC
  LIMIT 15
""").show(15, false)

println("\n=== TOP 10 WALLETS, CALM vs CRISIS, per family ===")
for (label <- Seq("USDC_CALM", "USDC_MAR2023_CRISIS", "UST_CALM", "UST_MAY2022_CRISIS")) {
  println(s"--- $label ---")
  spark.sql(s"""
    SELECT node_id, pagerank_score, rank_within_window
    FROM meridian.wallet_pagerank
    WHERE window_label = '$label' AND node_type = 'WALLET'
    ORDER BY rank_within_window
    LIMIT 10
  """).show(10, false)
}

println("\n=== CONCENTRATION: top-10-wallet PageRank mass / total wallet PageRank mass ===")
spark.sql("""
  WITH wallet_totals AS (
    SELECT window_label, SUM(pagerank_score) AS total_mass
    FROM meridian.wallet_pagerank
    WHERE node_type = 'WALLET'
    GROUP BY window_label
  ),
  top10_mass AS (
    SELECT window_label, SUM(pagerank_score) AS top10_mass
    FROM meridian.wallet_pagerank
    WHERE node_type = 'WALLET' AND rank_within_window <= 10
    GROUP BY window_label
  )
  SELECT t.window_label, t10.top10_mass, t.total_mass,
         ROUND(100.0 * t10.top10_mass / t.total_mass, 2) AS pct_mass_top10
  FROM wallet_totals t JOIN top10_mass t10 ON t.window_label = t10.window_label
  ORDER BY t.window_label
""").show(20, false)

System.exit(0)
