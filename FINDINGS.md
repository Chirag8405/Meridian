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
