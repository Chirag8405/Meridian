// Single source for every "i" tooltip on the site, so the wording stays
// consistent. Every statement here is taken from the repo (spark/*.scala,
// ingestion/*.py, backend/*.py, docs/FINDINGS.md, docs/ARCHITECTURE.md).
// Nothing here changes data, scoring or model output.

export type InfoContent = {
  /** What it means. */
  what: string;
  /** How it is computed (formula / method). */
  how?: string;
  /** Which Big Data tool or technique produced it. */
  tech?: string;
  /** How to interpret high vs low. */
  read?: string;
};

export const INFO = {
  // ---------------------------------------------------------------- score
  riskScore: {
    what: "A 0–100 stress score for one pool in one hour. 0 means a quiet, normal market; higher means trading looks more like the historical crises.",
    how: "100 × (0.40 × price + 0.25 × volume/trades + 0.15 × K-Means cluster + 0.20 × wallet concentration). Each of the four parts is first scaled to 0–1. Source: spark/risk_scores_baseline.scala.",
    tech: "Spark job (batch) for history; the Spark Structured Streaming job applies the same formula to live hours.",
    read: "Calm hours score roughly 4–5. Historical USDC crisis hours averaged 21.35 (the marker on each bar). Higher is worse; the score is descriptive, not a price forecast.",
  },
  priceDev: {
    what: "Price deviation: how far this hour's average price is from the pair's normal (calm-period) price, measured in standard deviations (σ).",
    how: "(hourly average implied price − calm mean) ÷ calm standard deviation, using the calm statistics in meridian.baseline_stats. Price severity = min(|σ| ÷ 20, 1). Carries 40% of the score.",
    tech: "Spark SQL aggregates over Hive tables (batch statistics); applied to live hours by the streaming job.",
    read: "Near 0 = trading at its usual price. A large negative value means well below normal. Negative or positive both count, because severity uses the absolute value.",
  },
  clusterSeverity: {
    what: "Which stress pattern K-Means assigned this hour to, converted to a severity from 0 to 1.",
    how: "K-Means (k = 4, chosen with an elbow + silhouette sweep over k = 2..10) groups hours by price, volume and trade-count deviation plus an anomaly flag. Severity lookup: cluster 0 (calm) = 0.05, cluster 1 (moderate USDC stress) = 0.5, cluster 2 (severe USDC stress) = 0.85, cluster 3 (UST zero-value trades) = 1.0. Carries only 15%, because the clusters are built from the same price and volume data and a higher weight would count them twice.",
    tech: "Spark MLlib K-Means. The model is frozen: live hours are scored with .transform() only and never re-fitted.",
    read: "0.05 is the calm cluster. Anything above that means the hour looks like a past stress pattern.",
  },
  walletConc: {
    what: "Wallet-concentration severity: how much of the trading flow sits with a few wallets, taken from the PageRank result.",
    how: "Share of PageRank mass held by the top-10 wallets in the matching window. Live rows use the constant USDC-calm value (about 0.128), so on live cards this part adds a fixed ≈2.6 points (0.20 × 12.83) and does not move with the market. It is set to 0 for UST rows because the signal came out backwards there.",
    tech: "Spark GraphX weighted PageRank over the wallet–pool graph.",
    read: "Higher means a few wallets dominate. Historically USDC went from 12.83% (calm) to 43.39% (crisis).",
  },
  volumeAnomaly: {
    what: "Volume / trade anomaly: how unusual the traded dollar volume and the number of trades are for that hour.",
    how: "Average of two capped severities: min(|volume z-score| ÷ 20, 1) and min(|trade-count z-score| ÷ 20, 1). Carries 25% of the score. The dashboard export does not include this one number per live row, so it is explained here rather than shown on the cards.",
    tech: "Spark SQL z-scores against meridian.baseline_stats.",
    read: "0 = a normal amount of trading. 1 = at or beyond 20 standard deviations from normal.",
  },
  scoreBar: {
    what: "The bar shows the score on its 0–100 scale. The thin vertical line is a reference marker.",
    how: "The marker sits at 21.35, the average risk score of USDC's real March 2023 crisis hours (from docs/FINDINGS.md). The bar turns red once the score reaches that marker.",
    read: "Bar short and left of the marker = calm. Bar past the marker = looks like a real crisis.",
  },
  sourceLive: {
    what: "Badge saying how the events behind this hour reached the system: \"live\" or \"gap-filled\".",
    how: "\"live\" = pushed over the Alchemy WebSocket as they happened (source alchemy_live). \"gap-filled\" = recovered afterwards with an eth_getLogs query for the blocks missed while the connection was down or the process was stopped (source alchemy_getlogs_replay). An hourly window is tagged gap-filled if any event in it came from that recovery.",
    tech: "ingestion/alchemy_live_feed.py (reconnect with backoff, state file, eth_getLogs replay). It is not the batch/Dune path.",
    read: "Gap-filled data is real on-chain data, only delivered late. It exists because a WebSocket does not replay what it missed.",
  },
  updated: {
    what: "How long ago the hourly window behind this reading started.",
    how: "Measured from the window's start time on your own clock. The streaming job only emits a window after a 2-hour watermark has passed it, so the newest reading always lags real time.",
    tech: "Spark Structured Streaming (1-hour windows, 2-hour watermark, 10-minute trigger).",
  },
  // ---------------------------------------------------------- live prices
  livePrice: {
    what: "Implied price per hour for one stablecoin pair, one line per exchange pool (Curve and Uniswap V2).",
    how: "Each swap gives a price = tokens received ÷ tokens sent (≈ 1.00 when the two coins trade one-for-one). The hourly value is the plain average of the valid swap prices in that hour (avg in spark/stream_alchemy_live.scala), not weighted by trade size.",
    tech: "Spark Structured Streaming 1-hour windows; stored in meridian.stablecoin_pool_hourly.",
    read: "A flat line near $1.00 is healthy. A sustained drop is a depeg. A single isolated spike on a tiny-volume hour is noise (see the note under the chart).",
  },
  dustToggle: {
    what: "A display-only filter that hides hours in which less than $1 was traded in total.",
    how: "Keeps hours with volume_usd ≥ 1. It changes nothing in the data, and the count of hidden hours is shown. Real depegs come with real volume, so they are not hidden by this filter.",
    read: "Turn it on to see the chart without dust-trade noise; leave it off to see every reading.",
  },
  // ------------------------------------------------------ recent activity
  recentWindow: {
    what: "How far back the counters and the bar chart look.",
    how: "15m = 1-minute bars, 1h = 5-minute bars, 6h = 30-minute bars, 24h = 2-hour bars (backend/activity.py). Always 12–15 bars.",
    tech: "FastAPI aggregation over the Supabase recent_swap_events table.",
  },
  recentFilters: {
    what: "Narrow the activity to one pair, one pool or one source (live vs gap-filled).",
    how: "Filters are applied server-side to the retained events before counting. \"untracked\" = a swap that is not one of the tracked pairs (for example a direct DAI↔USDT swap on Curve).",
  },
  swapsInWindow: {
    what: "Number of swaps the feed observed inside the selected time window.",
    how: "Counts events whose observed_at (when the feed saw them, not the on-chain time) falls inside the window. Older events still in the list below do not count here.",
    read: "0 means nothing was observed in this window. It does not mean the list below is empty: the list shows the latest retained events regardless of window.",
  },
  lastObserved: {
    what: "How long ago the feed last saw a swap (after the filters).",
    how: "Newest observed_at among the retained events. Not limited to the selected window.",
    read: "If this is old, the feed is paused or the pools are quiet. These pools trade roughly once every 15–20 minutes in calm conditions.",
  },
  activePools: {
    what: "How many of the three tracked pools had at least one swap in the window.",
    how: "Distinct pool names among the events in the window. The three pools are Curve 3pool, Uniswap V2 USDC/USDT and Uniswap V2 USDC/DAI.",
  },
  liveGap: {
    what: "Split of the window's swaps into live (pushed in real time) and gap-filled (recovered afterwards).",
    how: "See the live / gap-filled badge explanation. A restart of the feed produces a burst of gap-filled swaps, all stamped with the time they were recovered.",
  },
  activityChart: {
    what: "Bar chart of swaps per time bucket. Each bar is one bucket of the window.",
    how: "X axis: time in UTC (bucket start). Y axis: number of swaps observed in that bucket. Grey hairlines mark empty buckets. Click or focus a bar to list only that bucket's swaps.",
    tech: "Counts are descriptive only; they are not a risk signal.",
    read: "Gaps are normal: these pools trade intermittently.",
  },
  // ------------------------------------------------------------ risk strip
  baselineReliable: {
    what: "\"reliable baseline\": the pair had a genuine calm period in the data, so its score compares today against a trustworthy normal.",
    how: "The calm statistics come from December 2022 – May 2023 data (meridian.baseline_stats).",
  },
  baselineNone: {
    what: "\"elevated · no reliable baseline\": UST's pools were already unstable before this project's data begins, so there is no calm period to measure against.",
    how: "UST is scored against its own peg and its own full-history volume statistics instead, and the wallet-concentration part is set to 0. In this project, having no reliable baseline is itself treated as a risk signal.",
    tech: "Documented in docs/FINDINGS.md (\"UST has no reliable baseline\").",
    read: "UST scores of about 40–57 are the last readings before UST's data ends in June 2022, not a current state.",
  },
  asOf: {
    what: "Date of the last hour available for that pair.",
    how: "Each pair's dataset ends on a different date: current USDC pairs come from the live feed, UST ends on 2022-06-15.",
  },
  // ----------------------------------------------------------- crisis charts
  crisisChart: {
    what: "Hourly implied price of one pool during one real depeg.",
    how: "USDC: USDC/USDT on the Curve 3pool, 2023-03-08 to 03-15. UST: UST/USDC on a Curve metapool, 2022-05-07 to 05-16. Both use the same $0–$1.05 axis so the depth of each collapse is directly comparable.",
    tech: "Hourly rows from meridian.stablecoin_pool_hourly (Dune backfill), exported by Spark.",
    read: "The dashed line is the $1.00 peg. \"low\" marks the lowest hourly price. USDC dips and returns; UST falls to cents and never returns.",
  },
  // ------------------------------------------------------------ classifier
  classifierSplit: {
    what: "Cross-crisis test: train on one coin's crisis, test on the other's, which the model has never seen.",
    how: "Leave-one-coin-out validation. TEST_ON_UST trains on USDC and tests on all of UST. TEST_ON_USDC trains on UST (plus USDC calm hours) and tests on USDC's own crisis. Labels come from independently known crisis dates, not from our own scores.",
    tech: "Spark MLlib: logistic regression and random forest, compared with the rule-based risk score.",
    read: "A good score here means the model learned something general about depegs rather than memorising one coin.",
  },
  precision: {
    what: "Of the hours flagged as crisis, the share that really were crisis.",
    how: "true positives ÷ (true positives + false positives).",
    read: "High precision = few false alarms.",
  },
  recall: {
    what: "Of the hours that really were crisis, the share that were caught.",
    how: "true positives ÷ (true positives + false negatives).",
    read: "High recall = few missed crisis hours.",
  },
  f1: {
    what: "One number balancing precision and recall. This is the bar length.",
    how: "2 × precision × recall ÷ (precision + recall). Worked example: 100 crisis hours, a detector flags 80, of which 72 are real. Precision = 72/80 = 0.90, recall = 72/100 = 0.72, F1 = 2 × 0.90 × 0.72 ÷ 1.62 = 0.80.",
    read: "1.0 is perfect, 0 is useless.",
  },
  prauc: {
    what: "PR-AUC: precision–recall area under the curve.",
    how: "Sweeps every possible alert threshold and measures how well precision holds up as recall rises, then takes the area.",
    read: "1.0 is perfect. It judges the model across all thresholds, not just the one chosen.",
  },
  baselineWins: {
    what: "Why the rule-based baseline wins when testing on USDC.",
    how: "Its price and volume severities were built and validated on USDC crisis data, so for USDC it is close to in-distribution. The model trained on UST's total collapse transfers poorly to USDC's milder bank-run depeg: the two failures are structurally different. The training-size explanation was checked and rejected in docs/FINDINGS.md.",
    read: "The honest negative result matters: it shows the limit of the model instead of hiding it.",
  },
  // ----------------------------------------------------------------- wallets
  pagerank: {
    what: "PageRank scores how much trading flow passes through each address.",
    how: "Graph: nodes are wallet addresses and pools, edges are swap volume between them, in both directions and weighted by volume. GraphX's built-in PageRank ignores edge weights, so the project uses a custom weighted PageRank (Pregel). Output is stored in meridian.wallet_pagerank.",
    tech: "Spark GraphX, over about 135K wallet-level trades pulled from Dune.",
    read: "A high score means a lot of volume routes through the address. It does not mean an influential trader.",
  },
  influence: {
    what: "The address's PageRank score in that crisis window. The bar is scaled to the top row.",
    how: "PageRank score computed for that crisis window (meridian.wallet_pagerank, rank_within_window).",
  },
  contractType: {
    what: "\"contract\" = a smart contract (a router or aggregator). \"EOA\" = an externally owned account, i.e. a normal wallet controlled by a person.",
    how: "Checked with eth_getCode on each address: a contract has bytecode, an EOA has none. Stored in meridian.wallet_labels. It is not guessed from name patterns.",
    read: "Most top-ranked addresses are infrastructure, not traders.",
  },
  // -------------------------------------------------------------- evaluation
  threshold: {
    what: "The score level above which the system calls an hour \"elevated\".",
    how: "Calm-period mean + 2 standard deviations of risk_score, computed only from genuine calm history (USDC: 4.37 + 2 × 1.40 ≈ 7.18). UST has no calm history, so the USDC threshold is reused.",
    tech: "spark/evaluation_summary.scala.",
  },
  leadTime: {
    what: "How many hours before the depeg became visible in the price the score first raised a sustained alarm.",
    how: "Depeg onset comes from price alone, independent of the score: the first sustained hour where the price is 1% or more away from $1 (or invalid / zero-value). Both the warning and the onset need 2 or more consecutive hours, so one noisy hour does not count. Lead time = onset − first warning.",
    read: "72 h means three days of warning. 0 h for UST means the score was already elevated at the earliest data, so there is no \"before\" to measure, not that the score failed.",
  },
  magnitude: {
    what: "How far the price fell below $1.00 at its lowest hour.",
    how: "(1 − lowest hourly price) × 100.",
  },
  peakScore: {
    what: "The highest risk score during the crisis window.",
    how: "Maximum risk_score inside the labelled crisis dates.",
  },
  falseAlarms: {
    what: "Sustained elevated stretches outside the crisis window.",
    how: "Count of separate episodes of 2+ consecutive elevated hours in the surrounding history, outside the labelled crisis window (USDC: December 2022 – May 2023).",
    read: "Lower is better. USDC: 12 over about six months. UST's 34 are inflated because it has no calm baseline.",
  },
  stayedElevated: {
    what: "How many crisis-window hours the score stayed above the threshold.",
    how: "Total crisis hours minus hours below the threshold.",
    read: "168/168 = it never dropped below the alarm level during USDC's crisis.",
  },
  volumeRatio: {
    what: "Average trading volume in the crisis divided by the calm average.",
    how: "Volume in dollars, not pool reserves: reserve history is not available for the historical backfill.",
  },
  recovery: {
    what: "Whether and when the score returned to normal after the crisis.",
    how: "First hour after the window with the score back below the threshold. N/A for UST, which collapsed permanently.",
  },
  leadDiagram: {
    what: "Timeline from first warning to depeg onset.",
    how: "Left dot = first sustained alarm. Right dot = price-based depeg onset. The span between them is the lead time.",
    read: "A long span is good. A single red dot means the score was already high at the start of the data.",
  },
} satisfies Record<string, InfoContent>;

export type InfoKey = keyof typeof INFO;
