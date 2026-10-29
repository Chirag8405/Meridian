# Meridian: one-page summary

*Numbers are copied from `docs/FINDINGS.md` and `genai/eval/results/REPORT.md` as of 2026-10-25.
Items marked **[cite]** need a source before you state them in a presentation.*

## The problem
Stablecoins are meant to hold a $1 peg, and when one loses it the damage is fast. TerraUSD collapsed in
May 2022 and never recovered; USDC briefly lost its peg in March 2023 after its issuer disclosed exposure
to Silicon Valley Bank, then recovered. **[cite: size of losses / market impact; this repo has no such
figures.]** The warning signs (price, trading volume, trade counts, who is trading) are scattered across
many pools and are hard to read in real time, and reading them needs expertise. After an event, explaining
"when did the signals first show up?" is manual work.

## What Meridian does about it
1. **A big-data pipeline** (Hadoop, Hive, Spark; batch plus Spark Structured Streaming) ingests years of
   on-chain pool history from Dune and a live Alchemy WebSocket feed, into one Hive schema.
2. **A rule-based stress score (0-100)** combines price deviation (weight 0.40), volume and trade-count
   anomalies (0.25), a K-Means stress-pattern cluster (0.15) and wallet concentration (0.20).
3. **It is validated against the two real events** instead of assumed to work.
4. **A live dashboard** (Vercel, FastAPI on Render, Supabase) shows current scores, recent swap activity and
   the crisis charts; **a GenAI layer** explains the numbers.

## What was measured (not assumed)
| Question | Result |
|---|---|
| Early warning on USDC (Mar 2023) | **72 hours** lead time before a sustained 1% depeg; 12 brief false alarms in ~6 months of surrounding data; peak score 81.18 |
| Early warning on UST (May 2022) | **0 hours**: the data starts on 2022-04-15 when UST was already destabilised, so there is no "before" to measure. Reported, not hidden |
| Do top PageRank "influential wallets" represent traders? | No: 29 of the 35 top addresses are contracts (routers, bots), 83% |
| Does an ML classifier beat the rule score? | Trained on USDC, tested on UST: yes (F1 0.915 vs 0.858). Trained on UST, tested on USDC: no (F1 0.611 vs 0.995). Not general predictive power |
| Window-level check, USDC (708 windows, 22 positive) | Rule score: precision 0.60, recall 0.95, false-alarm rate 0.02. A plain 1% price alarm: precision 1.00, recall 0.41 (it fires only once the depeg is underway) |

## The GenAI part, and why it is trustworthy
- **The model never makes the risk call.** The pipeline computes the score; the LLM (Groq) explains and retrieves.
- **Grounded assistant:** answers questions using read-only tools over the same tables and BM25 search over the
  project docs, cites its sources, refuses investment advice and predictions, drops prompt-injection
  instructions, is rate limited, and every number in an answer is checked against the evidence it was shown.
- **Risk advisories:** a short plain-English reading of each live score, generated from that row's numbers only.

| GenAI measurement | Result |
|---|---|
| Assistant accuracy, 47 frozen test questions (gpt-oss-20b) | **36/47 (77%)** first run; **40/47 (85%)** after fixes (part of the change is run-to-run noise). Failures are listed in the report |
| Grounding check against deliberately wrong numbers | caught **117 of 122** |
| Advisories, 100 synthetic rows per model | no model invented a number; unrequested risk verdicts: gpt-oss-120b 97/100, gpt-oss-20b (production) 18/99, qwen3.8-27b 1/100 (heuristic detector) |
| Can an LLM flag an approaching depeg as well as the rule score? (USDC, 52 windows) | **No.** Rule: recall 0.95, no false alarms. gpt-oss-120b: recall 0.55, 23% false alarms. qwen3.8-27b: recall 0.41, none |

## Honest limits (say these out loud)
- Two historical events, one pair each: this is evidence for what it is, not a general predictor. Not financial advice.
- The GenAI results are small-sample, single-run, one model for chat, synthetic advisory rows. The 77% to 85% change
  after the fixes includes run-to-run noise.
- UST has no calm baseline in this dataset, so UST results are reported separately and never pooled.
- The judge comparison covers two events (UST cannot discriminate: every window is positive) and one run per window.

## One sentence
*"Meridian unifies scattered on-chain stablecoin signals at scale into a validated risk score, and uses a
grounded GenAI assistant, with measured accuracy and documented failures, so non-experts can query and understand it."*

## Where to look
`docs/FINDINGS.md` (all analysis) · `docs/ARCHITECTURE_DIAGRAM.md` (diagram) · `genai/eval/results/REPORT.md`
(GenAI numbers) · `docs/GENAI_ASSISTANT_PLAN.md` (design and every deviation) · live dashboard in the README.
