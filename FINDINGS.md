# Findings

Genuine analytical findings from working with the data — things worth
stating plainly in the project report, not implementation notes (see
`SETUP.md` for those) or architecture decisions (see `ARCHITECTURE.md`).

## UST has no reliable baseline in this dataset — and that's a finding, not a gap

**Computed in:** `spark/baseline_crisis_stats.scala`, stored in
`meridian.baseline_stats.baseline_status`.

### What we found

When computing baseline (calm-market) statistics for the risk model,
`UST_USDC`, `UST_USDT`, and `UST_DAI` all pass a naive sample-size check
(59–223 rows each, well above any small-n threshold) — but none of them
represent genuine calm behavior. Splitting each pair's non-crisis-window
data at the crisis boundary (2022-05-07) shows why:

| Pair | Sub-period | n | mean price | stddev |
|---|---|---|---|---|
| UST_USDC | pre-crisis (04-15 to 05-06) | 157 | $0.769 | 0.250 |
| UST_USDC | post-crisis (05-17 to 06-15) | 66 | $0.047 | 0.031 |
| UST_USDT | pre-crisis | 48 | $0.808 | 0.312 |
| UST_USDT | post-crisis | 11 | $0.044 | 0.035 |
| UST_DAI | pre-crisis | 64 | $1.0016 | 0.0018 |
| UST_DAI | post-crisis | 28 | $0.035 | 0.027 |

For `UST_USDC` and `UST_USDT`, the pool was **already showing meaningful
deviation from peg before our defined crisis window even starts** — the
May 7 boundary marks an acceleration, not the actual onset of instability.
For all three pairs, the post-crisis period isn't a return to normal, it's
UST sitting at a few cents with low variance simply because there's little
room left to fall further.

`UST_DAI`'s pre-crisis sub-period is the one exception worth noting: it
looks genuinely calm in isolation (mean≈$1.00, stddev=0.0018). But at n=64
over three weeks, immediately followed by total collapse, treating it as a
standalone reliable baseline would be a stretch — and using it would mean
applying a different reliability standard to `UST_DAI` than to the other
two UST pairs for no principled reason. All three are marked
`NO_RELIABLE_BASELINE`.

**Bottom line:** the entire window we have for UST (2022-04-15 to
2022-06-15) sits inside its collapse — lead-up, acute crisis, and dead
aftermath. There is no calm reference period captured anywhere in this
dataset for any UST pair. We deliberately did not backfill 2021 data (when
UST was genuinely stable) to manufacture one — see "Design implication"
below for why.

### Why this happened: UST's failure mode is structurally different from USDC's

USDC is collateral-backed — its March 2023 depeg was a bank-run-style
liquidity scare (SVB exposure) with a clear external trigger, and it
recovered within days once that trigger resolved (see the March 2023
baseline/crisis comparison: crisis stddev is ~8-10x baseline, but the mean
only dips to ~$0.98, and pre-crisis data is abundant and genuinely calm).

UST is algorithmic — its peg was maintained by a mint/burn arbitrage
mechanism against LUNA, not by holding real collateral. Once redemptions
outpaced the mechanism's ability to absorb them, there was no reserve
asset to fall back on, and the death spiral was self-reinforcing rather
than externally triggered and externally resolved. That's why the
instability shows up *before* our defined crisis window (arbitrage
pressure was already building) and never reverts (there was nothing to
revert to).

### Design implication for the risk-scoring model (flagged now, not retrofitted)

A stablecoin having **no reliable baseline is itself a risk signal**,
distinct from "a baseline exists and the current reading deviates from
it." Conflating the two would be wrong in both directions: scoring UST
against its own contaminated "baseline" would systematically understate
its risk (a price of $0.55 would look less anomalous against a
mean-of-$0.55 baseline than it should), and it would hide the more basic
fact that an asset with no demonstrable calm period is *already*
exhibiting the sign of interest.

The risk model should therefore route pairs down one of two paths based on
`baseline_status`:

- **`RELIABLE`** (USDC_USDT, USDC_DAI currently): score deviation from the
  pair's own baseline distribution (mean/stddev/percentiles) — this is the
  "how far from *its own* normal" question.
- **`NO_RELIABLE_BASELINE`** (UST_USDC, UST_USDT, UST_DAI currently): score
  on **absolute deviation from $1.00** and **trend/velocity of decline**
  instead — there's no "its own normal" to compare against, so the
  question becomes "how far from the peg every stablecoin is supposed to
  hold, and how fast is it getting worse."

This is a deliberate two-path design, not a workaround. Not built yet —
flagging it here so it's designed in when the risk-scoring model is built,
rather than discovered as a bug later.

## Most top-ranked "influential wallets" are actually infrastructure, not traders

**Computed in:** `spark/wallet_pagerank.scala`, addresses verified in
`ingestion/wallet_contract_check.py`, stored in `meridian.wallet_pagerank`
/ `meridian.wallet_labels`.

### What we found

Ran weighted PageRank on a bipartite wallet↔pool graph (135,164 individual
trades across the 4 tracked pools, ~11,800 distinct wallets). Took the 35
distinct addresses appearing in the top-15-overall or any window's top-10
wallet ranking and checked each via `eth_getCode` — a verifiable on-chain
fact, not a name-pattern guess.

**29 of those 35 addresses (83%) are contracts, not EOAs.** Only 6 are
plain wallets: `0x1090258d...`, `0x359377f7...`, `0x380e92c8...`,
`0x474890e5...`, `0x561f551f...`, `0x6aa6316c...`. Several of the
highest-ranked "wallets" have the "many leading zero bytes" address
pattern (e.g. `0x00000000008c4fb1c9...`, `0x0000000000753a65f1...`,
`0x0000000099cb7fc48a...`) — a known signature of CREATE2-mined vanity
addresses used by gas-optimized routers/MEV bots to reduce calldata cost.
One top-3 "wallet" in the USDC_CALM window, `0xb4e16d0168e52d35...`, is
the Uniswap V2 USDC/WETH pool itself (identified earlier in this project,
`ingestion/alchemy_live_feed.py`'s scoping work) — a pool acting as a
"taker" against our tracked pools, almost certainly from multi-hop routing
through it, not a real counterparty.

**This is load-bearing for how the results should be read.** A high
PageRank score for most of these addresses means "a lot of trade volume
routes through this," not "this address represents an influential trader
or whale." Presenting the raw ranking without this caveat would be
misleading — it would look like a list of powerful market participants
when it's mostly a list of DEX infrastructure. `meridian.wallet_labels`
exists specifically so this distinction stays queryable rather than
disappearing into an unlabeled ranking.

### Calm-vs-crisis wallet-influence concentration

The actual hypothesis under test: does wallet-influence concentrate into
fewer hands during a crisis? Measured as (top-10-wallet PageRank mass) /
(total wallet PageRank mass) per window:

| Window | % mass in top 10 wallets |
|---|---|
| USDC_CALM | 12.83% |
| **USDC_MAR2023_CRISIS** | **43.39%** |
| UST_CALM | 60.56% |
| UST_MAY2022_CRISIS | 52.57% |

**USDC strongly supports the hypothesis**: concentration more than
tripled during the crisis (12.83% → 43.39%) — consistent with a small set
of large arbitrageurs/institutional players stepping in to trade the SVB-
driven dislocation while smaller participants pulled back.

**UST does not support the hypothesis — but this comparison isn't clean
evidence either way.** Concentration was *slightly lower* during the
crisis than "calm" (60.56% → 52.57%), the opposite direction from USDC.
This should not be read as "UST didn't see the same concentration effect,"
because `UST_CALM` inherits the exact contamination documented above: it
isn't a genuine calm period, it's the pre-collapse instability and dead
post-collapse tail blended together (see `baseline_status =
'NO_RELIABLE_BASELINE'`). A more likely explanation is that UST trading
was concentrated among a small set of large players/bots for its *entire*
history in this dataset — before, during, and after the collapse — so the
calm/crisis split doesn't cleanly separate "normal" from "stressed"
behavior the way it does for USDC. This is consistent with, not
contradictory to, UST's algorithmic-collapse structural finding above:
there was no genuine "normal" period to compare against for concentration
either.

## Stress-pattern clustering (K-Means): separates by severity and coin, not just calm/crisis

**Computed in:** `spark/stress_clustering.scala`, stored in
`meridian.stress_clusters` / `meridian.stress_cluster_profiles`.

### Feature design: the UST fix had to extend beyond price

The original proposal was to give `NO_RELIABLE_BASELINE` (UST) pairs a
peg-deviation feature in place of a baseline z-score for **price** only,
consistent with the two-path risk-scoring design above. Checking
`baseline_stats` directly showed the same contamination problem applies to
**volume and trade_count** too: UST's `mean_volume_usd` /
`mean_trade_count` are computed over the identical pre/post-collapse
blended window as its price stats (e.g. `UST_USDC.mean_volume_usd =
$222,907.58` spans the non-calm window documented above), so scoring UST
volume/trade_count against those numbers would silently reintroduce the
exact problem the price fix was meant to solve.

**Fix applied**: extended the two-path design to all three deviation
features, not just price. `NO_RELIABLE_BASELINE` pairs' volume/trade_count
are z-scored against a **fresh, self-referential full-history mean/stddev
for that pair** (computed directly from the raw hourly data), not against
`baseline_stats`.

### Row counts — zero UST rows silently dropped

15,607 total `(pair, project, hour)` rows → 4 excluded (`NAN_PRICE`,
genuinely undefined 0/0, RELIABLE pairs only) → **15,603 rows feed
clustering**, all four features populated for every row. RELIABLE =
14,553; UST = 1,050 (829 valid-price + 221 `ZERO_VALUE_TRADE` rows,
imputed to `price_dev = -1.0` since a real trade executed at
~$0 — directionally correct and distinct from the z-score range used
elsewhere). One side finding: `anomaly_binary` is zero-variance within the
RELIABLE group (no RELIABLE row carries any flag besides the excluded
`NAN_PRICE` ones) — in this dataset it only does discriminating work on
UST's `ZERO_VALUE_TRADE` rows (21% of the UST group).

### k selection: elbow + silhouette, k=2..10

| k | WSSSE | silhouette |
|---|---|---|
| 2 | 46769.53 | 0.9501 |
| 3 | 22226.06 | 0.9838 |
| 4 | 18299.96 | 0.9848 |
| 5 | 14081.28 | 0.9862 |
| 6 | 12421.00 | 0.8844 |
| 7 | 10198.04 | 0.9868 |
| 8 | 8493.30 | 0.9149 |
| 9 | 7692.53 | 0.9153 |
| 10 | 8143.72 | 0.8763 |

Silhouette is high (0.88–0.99) across nearly every k tested — this is not
evidence that any k is a good fit. The feature space is one dense "calm"
mass plus far-flung outlier hours in standardized z-score terms, so almost
any partition trivially separates outliers from the mass with a high
average silhouette. k=6 and k=10 show real instability (silhouette dips,
and WSSSE actually *increases* from k=9→k=10 — a sign of a poor local
optimum, not a structural break in the data).

**Chose k=4**: sits at the point where WSSSE's percentage decrease starts
flattening, has strong silhouette (0.9848), and was sanity-checked against
the known crisis windows (below) before committing to it.

### Sanity check: does k=4 separate crisis from calm?

| period | cluster | count |
|---|---|---|
| USDC_CALM | 0 | 13,841 |
| USDC_CALM | 1 | 3 |
| USDC_CRISIS | 0 | 637 |
| USDC_CRISIS | 1 | 60 |
| USDC_CRISIS | 2 | 12 |
| UST_CRISIS | 0 | 455 |
| UST_CRISIS | 3 | 30 |
| UST_OTHER | 0 | 374 |
| UST_OTHER | 3 | 191 |

Cluster 0 absorbs ~98% of all rows, including most nominal "crisis-window"
hours — expected, since a crisis *date range* includes many hours that
aren't themselves extreme (depegs escalate and recover, they aren't
uniformly severe throughout their labeled window). The three small
clusters aren't noise: they separate cleanly by **severity and coin**,
not just a binary calm/crisis split — cluster 2 (12 rows) is USDC's most
extreme hours, cluster 1 (60 rows) is moderately-stressed USDC hours, and
cluster 3 (221 rows) is a UST-specific stress signature distinct from
USDC entirely. This matches the actual goal (distinguishing *types/stages*
of crisis behavior) better than a coarser k would have.

### What each cluster actually represents

`meridian.stress_cluster_profiles` (full 15,603-row dataset, `k=4`):

| cluster | n_rows | avg price_dev | avg volume_dev | avg trade_count_dev | pct_ust | usdc_crisis | ust_crisis |
|---|---|---|---|---|---|---|---|
| 0 | 15,307 | -0.10 | 0.03 | 0.11 | 5.4% | 637 | 455 |
| 1 | 63 | -18.77 | 30.05 | 40.58 | 0% | 60 | 0 |
| 2 | 12 | -74.21 | 18.50 | 59.43 | 0% | 12 | 0 |
| 3 | 221 | -1.00 | -0.46 | -0.48 | 100% | 0 | 30 |

Reading this against the crisis-window sanity check above:

- **Cluster 0 — baseline/quiet**: near-zero deviation on every feature,
  98.1% of all rows. This includes hours *inside* the officially-labeled
  crisis windows (637 USDC, 455 UST) that simply weren't extreme by these
  features — confirms depeg windows aren't uniformly severe hour-to-hour.
- **Cluster 1 — moderate USDC stress**: 63 rows, exclusively RELIABLE
  pairs, large but not extreme deviation (price ~19σ below baseline,
  volume/trade_count ~30-40σ above) — a volume/activity surge with a real
  but partial price dip. 60 of 63 fall inside the USDC Mar 2023 window.
- **Cluster 2 — severe USDC stress**: only 12 rows, the most extreme price
  deviation observed (~74σ), all 12 inside the USDC crisis window — the
  acute peak of the SVB-driven depeg.
- **Cluster 3 — UST zero-value-trade signature**: 221 rows, `avg_price_dev
  = -1.00` *exactly* and `pct_ust_rows = 100%` — this cluster is precisely
  and completely the 221 imputed `ZERO_VALUE_TRADE` rows, nothing more and
  nothing less. Every zero-value UST trade landed here, and no other row
  did. This is a clean validation of the imputation choice: treating a
  genuinely-zero-value trade as `price_dev = -1.0` gave the algorithm a
  distinct, coherent signature rather than noise scattered across other
  clusters — and it's the one cluster that isn't purely about price
  severity, since 91% of these rows (191/221) fall *outside* the
  officially-labeled UST crisis window (2022-05-07 to 2022-05-16),
  confirming zero-value trades occurred both during and after the
  officially-dated crisis window.

Net result: k=4 delivers on the actual goal — distinguishing calm from
multiple distinct *types and stages* of stress (moderate vs. severe USDC
price stress, and a wholly separate UST worthless-trade signature), not
just a binary calm/crisis split.

## Rule-based baseline risk score: validates against known crisis windows, and surfaces a new finding along the way

**Computed in:** `spark/risk_scores_baseline.scala`, stored in
`meridian.risk_scores_baseline`. Built deliberately *before* any ML model
training, so a trained model has a concrete, explainable baseline to
validate against rather than nothing.

### Formula

`risk_score` (0-100) = `100 * (0.40*price_severity + 0.25*volume_trade_severity
+ 0.15*cluster_severity + 0.20*wallet_concentration_severity)`, where each
component is independently normalized to `[0,1]` first (see
`hive/risk_scores_baseline_schema.sql` for the full per-component design and
the reasoning behind each weight/cap — decided and confirmed before
implementing, same as the clustering design). Two points worth restating
here:

- **Cluster severity is intentionally low-weighted (0.15)** relative to
  price/volume (0.65 combined) — cluster membership is *derived from*
  those same features via K-Means, so a higher weight would double-count
  the same signal rather than add independent information.
- **Wallet-concentration is zeroed out for all UST rows.** The signal is
  validated as risk-increasing for USDC (12.83% calm → 43.39% crisis
  concentration) but inverted for UST (60.56% "calm" → 52.57% crisis) — a
  direct consequence of `UST_CALM`'s baseline contamination documented
  above. Using it for UST would encode a backwards signal on every UST
  row, so it contributes 0 there rather than something misleading.

### Cluster → severity mapping

Grounded in each cluster's actual raw price/volume/trade_count profile
(not assumed — see the K-Means section above for the full table): cluster
0 (calm) = 0.05, cluster 1 (moderate USDC stress) = 0.5, cluster 2 (severe
USDC stress, most extreme z-score) = 0.85, cluster 3 (UST zero-value-trade
signature) = 1.0. Cluster 3 ranks *above* cluster 2 despite a numerically
smaller `price_dev` (-1.0 vs. -74σ), because it represents a categorically
different, worse outcome — a literal $0 trade (total peg failure), not a
statistically-extreme partial depeg.

### Validation: known-calm vs. known-crisis score distributions

| period | n | avg | median | min | max | p90 |
|---|---|---|---|---|---|---|
| RELIABLE_CALM | 13,844 | 4.73 | 4.36 | 3.34 | 62.78 | 6.11 |
| USDC_CRISIS | 709 | 21.35 | 12.19 | 9.55 | 86.43 | 55.64 |
| UST_CRISIS | 485 | 27.46 | 30.70 | 1.24 | 56.62 | 40.13 |
| UST_OTHER | 565 | 30.79 | 38.77 | 1.45 | 56.62 | 56.62 |

**The score does what it's supposed to**: calm hours sit tightly around a
median of 4.36 (p90 only 6.11 — the calm cluster is genuinely quiet), while
every crisis-labeled category sits far higher (medians 12–39, well above
calm's p90). USDC's crisis max (86.43) correctly captures the acute SVB-
depeg peak hours.

**Two things worth explaining, not glossing over:**

1. **UST_CRISIS's minimum (1.24) is lower than RELIABLE_CALM's minimum
   (3.34)** — at first glance this looks backwards. It isn't a scoring
   failure: it's a combination of (a) legitimate sub-hour variation within
   the labeled crisis window, and (b) a direct, expected side effect of
   zeroing `wallet_concentration_severity` for UST.

   The actual lowest-scoring row is `UST_DAI / curve / 2022-05-07
   21:00:00` — the first day of the hand-drawn crisis window. Its raw
   values: `implied_price = $0.9952` (essentially still at peg),
   `volume_usd = $996,957`, `trade_count = 8`, `is_valid_price = true`,
   `cluster_id = 0` (the calm cluster — the clustering algorithm agrees,
   independently). This pool genuinely hadn't been hit by the collapse yet
   at that specific hour, even though its date falls inside the window —
   the same "crisis windows aren't uniformly severe hour-to-hour" pattern
   documented in the clustering section above.

   Separately, `wallet_concentration_severity` contributes ~2.6 points to
   every RELIABLE row's floor (0.20 × 12.83% × 100), a floor UST rows never
   get since that component is zeroed for them. So an unremarkable UST
   hour can score lower than an unremarkable USDC hour purely from that
   confirmed design choice, on top of the genuine calm-hour effect above —
   not a defect, but two compounding, explained causes rather than one.
2. **`UST_OTHER` scores higher on average than the officially-labeled
   `UST_CRISIS` window** (median 38.77 vs. 30.70). Part of this is the
   cluster-3 row split noted in the clustering section: of the 221
   zero-value-trade rows (severity 1.0 — the single biggest driver of a
   high score), only 30 fall inside the hand-drawn 2022-05-07 to
   2022-05-16 crisis window; 191 fall outside it, in `UST_OTHER`.

   But splitting `UST_OTHER` by sub-period shows a second, more important
   mechanism at work — and a genuine limitation of a pure deviation-based
   score, not just a date-boundary artifact:

   | sub-period | n | avg risk_score | avg price_severity |
   |---|---|---|---|
   | PRE_CRISIS_BUILDUP (2022-04-15 to 05-06) | 425 | 26.31 | 0.475 |
   | POST_CRISIS_DEAD (2022-05-17 to 06-15) | 140 | 44.39 | 0.967 |

   The post-collapse period — UST sitting dead at a few cents, per the
   baseline-contamination finding above — scores nearly **twice as high**
   as the actual pre-crisis buildup period, and its `price_severity` is
   almost fully saturated (0.967 of a max 1.0). This is because
   `price_severity = min(|implied_price - 1.00|, 1.0)` is a pure magnitude
   measure: it has no notion of trend, velocity, or "already fully
   realized" vs. "just now emerging." A stablecoin sitting permanently
   near $0.04 scores about as high, indefinitely, as the literal moment of
   a $0 trade — while the pre-crisis buildup period, still near-peg but
   destabilizing (arguably the more actionable signal for an *early*-
   warning system), scores meaningfully lower simply because price hadn't
   collapsed yet.

   **Known limitation, stated plainly**: `price_severity` measures the
   *magnitude* of deviation from peg, not trend or trajectory. It cannot
   distinguish "actively destabilizing" (early-warning-relevant — this is
   the behavior the whole project exists to catch early) from "already
   fully collapsed and static" (no longer actionable — the warning would
   be far too late). Worse, it currently scores the latter *higher* than
   the former (0.967 vs. 0.475 avg `price_severity` above), which is
   backwards for an early-warning use case. Fixing this needs a
   trend/velocity term (e.g. rate of change in `price_dev` over recent
   hours), which is a natural candidate for the eventual ML model to add
   on top of this baseline — not something to patch into the rule-based
   score after the fact.

## ML crisis classifier: beats the baseline generalizing mild→severe, loses badly severe→mild

**Computed in:** `spark/crisis_features.scala` (features/labels, stored in
`meridian.crisis_features`) and `spark/crisis_classifier.scala` (training/
evaluation, stored in `meridian.crisis_classifier_predictions` /
`meridian.crisis_classifier_metrics`). Built specifically to test whether a
trained model, given trend/velocity features, can fix the rule-based
baseline's documented blind spot above (magnitude-only, no trajectory).

### Design decisions, confirmed before implementing

- **Trend/velocity features use time-based windows, not row-count ones.**
  Real gaps exist in the hourly series (as low as 17% coverage for
  UST_DAI — a row only exists if a qualifying trade happened that hour).
  `price_severity_velocity` is the actual rate of change per elapsed hour
  (NULL, not zero, when the previous row is >6h away), and the 3-hour
  rolling mean/slope use a genuine `RANGE BETWEEN INTERVAL 3 HOURS
  PRECEDING` frame so a gap doesn't silently stretch the window.
- **Binary CALM/CRISIS labels, grounded in independently-known historical
  crisis dates, not derived from any of our own severity metrics**
  (`cluster_id`, `cluster_severity`, `risk_score`) — using our own scores
  as ground truth would let a "beat the baseline" model partly learn to
  just reproduce the baseline. USDC: CRISIS = 2023-03-08 to 03-15 only.
  UST: **every row is CRISIS** — both the pre-window buildup (already
  meaningfully unstable, per the no-reliable-baseline finding above) and
  the post-window collapsed/pinned-near-zero period are treated as
  not-calm, consistent with that same finding. This means UST contributes
  zero CALM examples anywhere in this dataset.
- **Leave-one-coin-out validation, asymmetric by necessity**: because UST
  has no CALM rows to offer, `TEST_ON_UST` is a pure single-coin split
  (train on USDC calm+crisis, test on USDC calm holdout + all of UST), but
  `TEST_ON_USDC` is necessarily coin-blended for the CALM class (train on
  USDC calm + all of UST-as-CRISIS, test on USDC calm holdout + USDC's own
  crisis, held out entirely). This deviation from strict single-coin LOCO
  is deliberate and documented here, not accidental.
- **Feature set excludes `cluster_severity` and `risk_score`** (hand-
  assigned crisis-severity judgments, too close to the label) but
  initially included `wallet_concentration_severity` — this had to be
  removed after the first training run; see below.

### A leakage-adjacent feature had to be found and removed

The first training run showed `wallet_concentration_severity` dominating
Random Forest's feature importances (0.53–0.82, far ahead of everything
else) — which on inspection was a red flag, not a good result. Unlike
`price_severity`/`volume_trade_severity` (computed per-row), that feature
is a **constant broadcast per named window**: every USDC row gets exactly
0.1283 (calm) or 0.4339 (crisis) depending only on which window it falls
in, and every UST row gets exactly 0.0. For USDC's training data, that's
effectively a two-value direct proxy for the label itself, not a graded
severity signal the model had to learn to interpret. Retrained without it.

### Results (same held-out test rows, model vs. rule-based baseline)

| direction | scorer | precision | recall | F1 | PR-AUC |
|---|---|---|---|---|---|
| TEST_ON_UST | logistic_regression | 0.992 | 0.850 | **0.915** | **0.918** |
| TEST_ON_UST | random_forest | 0.894 | 0.826 | 0.858 | 0.899 |
| TEST_ON_UST | rule_based_baseline | 0.988 | 0.759 | 0.858 | 0.836 |
| TEST_ON_USDC | logistic_regression | 0.791 | 0.391 | 0.523 | 0.587 |
| TEST_ON_USDC | random_forest | 0.717 | 0.532 | 0.611 | 0.610 |
| TEST_ON_USDC | rule_based_baseline | 0.990 | 1.000 | **0.995** | **0.994** |

**Direction TEST_ON_UST — the model genuinely beats the baseline.** A
model trained *only* on USDC's milder, bank-run-style depeg pattern
correctly flags 85% of UST's structurally different algorithmic-collapse
crisis hours (Logistic Regression: F1 0.915, PR-AUC 0.918, both above the
baseline's 0.858/0.836) at very high precision (0.992). This is genuine
cross-coin generalization, not a coin-identity shortcut — the leaky
feature that could have explained a false positive result here was already
removed before this run.

**Direction TEST_ON_USDC — the baseline wins decisively.** A model
trained on UST's crisis pattern (which, per the label design above,
includes everything from early destabilization to total collapse) misses
roughly half of USDC's actual crisis hours (best recall 0.532) when
tested against USDC's milder, partial depeg.

The original design discussion flagged two possible contributing factors
here: harder pattern transfer (severe→mild), and a training-size
asymmetry. **Only the first holds up against the actual training data —
the training-size concern doesn't apply to what was actually built and
should be retracted, not repeated.** The training-size worry was valid
against the *original* pre-redesign LOCO plan (each coin training on its
own calm+crisis data, giving UST only ~1,050 rows), but the redesign
confirmed for the leave-one-coin-out split (both directions draw CALM
rows from the same 11,579-row USDC pool, since UST has none) resolved it:
per the job log, `Direction TEST_ON_USDC` actually trains on **more**
total rows (12,629 vs. 12,288) and **more** crisis-class rows (1,050 UST
vs. 709 USDC) than `Direction TEST_ON_UST`, not fewer. So this direction's
weaker result is attributable to harder pattern transfer alone — training
on a severe/collapsed pattern doesn't transfer well to detecting a milder
one, because the underlying failure modes are structurally different
(algorithmic death spiral vs. collateral-backed bank-run), not because of
a training-data shortage. The baseline's near-perfect performance here
(F1 0.995) makes sense too: `price_severity` and `volume_trade_severity`
were literally validated against USDC crisis data during the baseline's
own construction, so this is close to in-distribution territory for it.

### Did the trend/velocity features actually help? A more precise answer than "yes"

Feature importances (Random Forest, both directions) after removing the
leaky feature:

| feature | TEST_ON_UST | TEST_ON_USDC |
|---|---|---|
| price_severity_rolling_mean_3h | 0.42 | 0.41 |
| volume_trade_severity | 0.25 | 0.23 |
| price_severity | 0.23 | 0.28 |
| price_severity_velocity | 0.03 | 0.04 |
| price_severity_rolling_slope_3h | 0.03 | 0.01 |
| cluster_id (one-hot, summed) | 0.05 | 0.03 |
| trend_available flag | ~0.00 | 0.01 |

The **rolling mean** (a smoothed recent-severity average) is consistently
the single most important feature in both directions — meaningfully ahead
of the raw point-in-time `price_severity` it's smoothing. But the features
built specifically to capture *directionality* — `price_severity_velocity`
(hour-over-hour rate) and `price_severity_rolling_slope_3h` (3-hour trend)
— contribute only marginally (0.01–0.04) in both models. **The honest
finding is narrower than "trend/velocity fixed the baseline's blind
spot": noise-reduction via smoothing helped meaningfully, but genuine
trajectory/direction signal contributed only a small, secondary amount.**
Whether a longer lookback window, a different velocity formulation, or
more training data would change this is an open question for future work,
not something this pass resolves.
