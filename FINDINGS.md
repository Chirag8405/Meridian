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
