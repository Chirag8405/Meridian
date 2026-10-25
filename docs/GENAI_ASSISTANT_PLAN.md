# Plan: Grounded GenAI Assistant, Faithfulness Evaluation, and LLM-vs-Rules Judge

Status: PLAN ONLY. Nothing in this document is implemented yet unless the
"Current state" section says so. Written 2026-10-25.

This document is written so that an AI agent (or a human) with no prior
conversation context can continue the work without guessing. Read it fully
before writing code. The rules in "Rules for the implementing agent" apply to
every step.

---

## 1. Why this exists (the problem statement)

Stablecoin depegs are fast and costly (TerraUSD, May 2022; USDC after its
issuer disclosed Silicon Valley Bank exposure, March 2023). The warning signals
(price, liquidity, volume, wallet behaviour) are scattered, and interpreting a
number such as "risk score 7.7, cluster severity 0.05" needs expertise.

Meridian already solves the *data and scoring* half: a big-data pipeline and a
rule-based multi-signal risk score, validated on two real events. This plan adds
the *understanding and trust* half using GenAI, in three connected parts:

| Part | Name | Problem it addresses |
|---|---|---|
| A | Grounded assistant (chat) | A non-expert can ask questions about the data and findings and get answers that cite the exact rows/sections used. |
| B | Faithfulness evaluation | Evidence that LLM output (chat answers and the existing risk advisories) is factually tied to the data, instead of a demo that merely sounds right. |
| C | LLM-as-judge vs rule-based score | A controlled, honest experiment: can an LLM, shown anonymised feature windows, flag stress as well as the rule-based `risk_score`? Includes the result even if the LLM loses. |

One-sentence framing for presentations: *"Meridian unifies scattered on-chain
stablecoin signals at scale into a validated risk score, and uses a grounded
GenAI assistant, with measured factual accuracy, so non-experts can query and
understand it."*

The model never produces the risk assessment. The rule-based pipeline computes
it; the model only explains, retrieves, and is itself evaluated.

### Claims this project must NOT make
- Not a depeg *predictor* and not financial advice. `docs/FINDINGS.md` states:
  72h lead time on USDC (one event); zero on UST (data begins when UST was
  already destabilised). Both results are reported; keep reporting both.
- Do not call the LLM judge (Part C) "better" unless the measured numbers say so.
- Loss/market-size figures for the real events are NOT in this repo. Do not put
  dollar figures in the product or docs unless a citable source is added.

---

## 2. Current state (verified in the repo on 2026-10-25)

Read `CLAUDE.md` first; it has the authoritative stack, JDK split, and
conventions. Facts below were checked against files, not assumed.

### 2.1 Architecture relevant to this plan
- Pipeline: Hadoop/Hive/Spark batch + a Spark Structured Streaming consumer
  (`spark/stream_alchemy_live.scala`) -> `spark/export_dashboard_data.scala`
  writes JSON to `dashboard/data/` -> `ingestion/push_to_supabase.py` pushes to
  Supabase -> `backend/main.py` (FastAPI on Render) serves -> Next.js on Vercel.
- The publish job is `systemd/publish-dashboard.sh`, run every 2 hours by
  `meridian-dashboard-publish.timer`: Spark export -> `ingestion/generate_risk_advisories.py`
  -> `ingestion/push_to_supabase.py`.
- Render service: `Meridian`, id `srv-dap8af6gekts738556ug`, URL
  `https://meridian-czv0.onrender.com`, auto-deploys from `main`.
  Render CLI and Supabase CLI are installed in `~/.local/bin`. Render CLI is
  logged in (workspace "My Workspace" `tea-d3uvligdl3ps73fej87g`); Supabase CLI
  is installed but may not be logged in.
- Browser never calls Render directly (Render API has no CORS). The dashboard
  uses Next.js Route Handlers as proxies, e.g.
  `dashboard/app/api/recent-swap-activity/route.ts`. Follow that pattern.
- The backend currently has dependencies `fastapi`, `uvicorn[standard]`, `httpx`
  only (`backend/requirements.txt`). The backend is read-only against Supabase
  using the *publishable* key and RLS SELECT-only policies. Keep it that way.
- Backend `_fetch_table()` pages with `Range` headers (PostgREST caps responses
  at 1000 rows). Reuse it; do not write a second fetcher without paging.

### 2.2 Existing GenAI component (the only one)
`ingestion/generate_risk_advisories.py`:
- Runs inside the 2-hourly publish job (batch, not on demand).
- Reads local `dashboard/data/current_risk_live.json`, calls Groq's REST API
  with `requests` (not the Groq SDK), model constant `MODEL =
  "openai/gpt-oss-20b"`, writes an `advisory` string per row back to that JSON;
  `push_to_supabase.py` stores it in `current_risk_live.advisory`.
- Prompt inputs: pair, project, risk_score, price_dev, cluster_id,
  cluster_severity, wallet_concentration_severity, all formatted to 4 decimals
  by `fmt()`. No trend, no history.
- If Groq fails or the generation is cut off (`finish_reason == "length"`), that
  row gets `advisory = null` and the card shows no text. Publishing never blocks
  on the model.
- `GROQ_API_KEY` exists only in the local `.env` (see `.env.example`). It is NOT
  set on Render or Vercel.
- `CLAUDE.md` still says "No GenAI/generative components yet". That line is
  stale. Updating it is part of Phase 0.

### 2.3 Data available (Supabase tables, mirrored in `supabase/schema.sql` and
`dashboard/lib/data.ts` types). Column names below are exact.

| Table | Rows (checked) | Key columns |
|---|---|---|
| `current_risk` | 7 | pair, project, baseline_status (`RELIABLE`/`NO_RELIABLE_BASELINE`), risk_score, dt, window_start_ts |
| `current_risk_live` | 4 | pair, project, risk_score, window_start_ts, source, price_dev, cluster_id, cluster_severity, wallet_concentration_severity, advisory |
| `usdc_crisis_timeline` | 191 | window_start_ts, implied_price, volume_usd (hourly, 2023-03-08..2023-03-15 window) |
| `ust_crisis_timeline` | 182 | same columns (2022-05-07..2022-05-16 window) |
| `live_price_timeline` | ~1618 | pair, project, window_start_ts, implied_price, volume_usd |
| `evaluation_summary` | 2 | event_label (`USDC_MAR2023`, `UST_MAY2022`), threshold_basis, calm_mean, calm_stdev, calm_n, elevated_threshold, depeg_onset_ts, first_warning_ts, lead_time_hours, false_alarm_count, peak_score, min_score_during_crisis, crisis_hours_total, crisis_hours_below_threshold, recovery_*, depeg_magnitude_pct, min_price, calm_avg_volume_usd, crisis_avg_volume_usd, calm_caveat |
| `classifier_metrics` | 6 | direction, scorer, n_test, n_test_crisis, precision_crisis, recall_crisis, f1_crisis, pr_auc, threshold_used |
| `wallet_rankings` | 20 | window_label, node_id, pagerank_score, rank_within_window, is_contract, label |
| `recent_swap_events` | ~105 (retention ~100 rows / 48h) | event_id, tx_hash, log_index, event_ts, observed_at, pair, project, pool_name, pool_address, implied_price, source |
| `metadata` | 1 | id, exported_at, dataset_end_usdc, dataset_end_ust, usdc_crisis_window, ust_crisis_window |

Verified facts the assistant must be able to reproduce from the data
(from `evaluation_summary` and `docs/FINDINGS.md` "Does the risk score provide
genuine early warning"):
- USDC_MAR2023: elevated_threshold 7.18 (calm mean 4.37, stdev 1.40, n=4107),
  first_warning_ts 2023-03-08T00:00:00Z, depeg_onset_ts 2023-03-11T00:00:00Z,
  lead_time_hours 72.0, false_alarm_count 12, peak_score 81.18,
  depeg_magnitude_pct 11.92, min_price 0.8808.
- UST_MAY2022: threshold_basis `cross_pair_from_usdc`, same 7.18 threshold,
  lead_time_hours 0.0, false_alarm_count 34, peak_score 56.31,
  depeg_onset_ts = first_warning_ts = 2022-04-15T04:00:00Z (the first hour of
  available data; UST had no RELIABLE calm baseline, see `calm_caveat`).
- Live tracking is USDC only (pairs USDC_DAI, USDC_USDT; DEXs curve and
  uniswap_v2). UST has no live pool activity.

### 2.4 Gotchas that have already caused bugs
- Local JSON exports carry timestamps with `+05:30` (the Spark session
  timezone); the Render API returns UTC (`+00:00`). Tools in this plan must read
  from the Render/Supabase side and present everything as UTC.
- `current_risk` rows can have an old `window_start_ts` per pair (a pair that
  has not traded recently keeps its last window). "Latest" is per (pair,
  project), not global.
- `recent_swap_events` retention is bounded (about 100 rows / 48h). Never state
  coverage beyond that.
- `stress_clusters` is a batch-only Hive table with NO live-window rows. Do not
  join it for live data (that mistake caused an empty "Live now" section).
- Supabase PostgREST returns max 1000 rows per request; always page.
- Never re-fit ML models on historical+live data (see `CLAUDE.md` "Guarantee").
  This plan does not touch models; do not add any fitting.

---

## 3. Verified vs. unverified (do not guess the second list)

### Unverified at time of writing (items 1-6 were resolved in Phase 0, see Appendix A; anything not listed there is still unverified)
1. Whether the chosen Groq model supports tool/function calling with the
   OpenAI-compatible chat API. Check Groq's current docs, then run a 1-call
   smoke test. If it does not, fall back to the "deterministic retrieval, then
   answer" design in 5.2 (no model-driven tool calls).
2. Groq free-tier rate limits (requests/min, tokens/min, daily caps) for the
   chosen model. Look them up; do not assume numbers. Design the limiter from
   the real numbers.
3. Whether Groq offers an embeddings endpoint. This plan deliberately does NOT
   need one (lexical retrieval, 5.3). Do not add embeddings without asking.
4. Whether Render's build for the `Meridian` service has the repository root or
   `backend/` as its root directory, i.e. whether files outside `backend/`
   (e.g. `docs/FINDINGS.md`) are available at runtime. Check with
   `render services -o json --confirm` and the build settings. If only
   `backend/` ships, the retrieval corpus must be generated into `backend/`
   (see 5.3, which assumes this to be safe).
5. Python version on Render (affects syntax like `X | None`; current
   `backend/main.py` already uses it, so >= 3.10 holds today).
6. Current Groq model ids. `openai/gpt-oss-20b` is in use today. The earlier
   suggestion `llama-3.1-8b-instant` was NOT verified to exist or be
   appropriate. Resolve via Groq's model list at implementation time.

### Verified by reading the repo
Everything in section 2.

---

## 4. Rules for the implementing agent (anti-hallucination)

1. Do not invent table names, columns, endpoints, env vars, model ids, or
   library APIs. If it is not in section 2 or in a file you opened, open the
   file or check the docs first.
2. Every number the assistant shows must come from a tool result or a retrieved
   document in the same turn. The post-hoc grounding check (5.5) enforces this;
   do not weaken it to make tests pass.
3. Read `docs/FINDINGS.md` before writing any prompt that talks about results.
   Do not paraphrase findings from memory.
4. Do not add risk predictions, trading advice, or causal claims to prompts or
   outputs. Descriptive only, same as the Recent activity section.
5. Follow `CLAUDE.md` conventions: new code in clearly separated directories;
   document every new env var/config in `docs/SETUP.md` immediately; long jobs
   via `nohup`; never change system-wide JAVA_HOME or the archlinux-java
   default; no HBase/Zookeeper.
6. The Render backend stays read-only toward Supabase. No secret/service key on
   Render or Vercel.
7. Secrets: `GROQ_API_KEY` must never reach the browser, git, logs, or
   responses. Adding it to Render is a manual secret step (see 5.7); ask the
   user rather than guessing at credentials.
8. Evaluation honesty: report negative and inconclusive results. Do not tune
   prompts on the final evaluation questions (keep a dev set and a test set,
   see 6.2).
9. Before claiming something works, run it and show the output. Before opening a
   PR, run the verification commands in section 9.
10. Outward-facing or hard-to-reverse actions (deploys, DB schema changes,
    publishing data, merging PRs) need the user's confirmation. Merging has so
    far required an explicit "merge it" from the user each time.
11. Ask the user (do not decide silently) on the open decisions in section 10.

---

## 5. Part A: Grounded assistant

### 5.1 Behaviour
- A chat page where the user asks questions such as:
  - "Which pool has the highest live risk score right now?"
  - "What was the lead time on USDC in March 2023, and how was it measured?"
  - "Why does UST show zero lead time?"
  - "How many swaps did the feed observe in the last hour?"
- Answers are 2-6 short sentences, plain English, with citations like `[S1]`
  that map to a "Sources" list returned alongside the answer. A source is either
  a data row (table + key + fetched-at) or a document chunk (file + heading).
- Refusals (fixed wording, no model improvisation needed):
  - Financial advice / "should I buy/sell": say Meridian is descriptive, not
    advice.
  - Predictions ("will X depeg tomorrow"): say the score describes current
    stress; the measured early-warning evidence is two events (cite FINDINGS).
  - Out of scope / unknown: say the data does not contain it.
- Never claims a cause the data does not establish (same rule as advisories).

### 5.2 Design (keep it simple and auditable)
Two-stage pipeline in `backend/assistant/`, one endpoint:

`POST /api/assistant/chat` body `{ "question": str (<=500 chars),
"history": [] (optional, last <=4 turns) }` -> `{ "answer": str,
"sources": [...], "grounding": {"checked": bool, "ungrounded_numbers": []},
"refused": bool }`.

Stage 1, evidence gathering (tools implemented as plain Python functions over
Supabase; never raw SQL, never model-written queries):

| Tool | Returns | Backed by |
|---|---|---|
| `get_live_risk(pair?, project?)` | rows from `current_risk_live` | table |
| `get_historical_risk(pair?, project?)` | rows from `current_risk` | table |
| `get_event_evaluation(event_label?)` | rows from `evaluation_summary` | table |
| `get_event_timeline(event, start?, end?)` | hourly rows, downsampled/summarised (min/max/first-depeg hour) rather than all 190 rows | `usdc_crisis_timeline` / `ust_crisis_timeline` |
| `get_live_prices(pair, project, hours)` | summarised from `live_price_timeline` | table |
| `get_recent_activity(window, pair?, pool?, source?)` | the aggregation already in `recent_swap_activity` logic (reuse the function, do not duplicate it) | `recent_swap_events` |
| `get_classifier_metrics()` | rows | `classifier_metrics` |
| `get_wallet_rankings(window_label?)` | rows | `wallet_rankings` |
| `search_docs(query, k=4)` | top-k chunks from the findings corpus | 5.3 |

If tool calling is verified (3.1): let the model choose tools via the
chat-completions `tools` parameter, max 3 tool calls per question.
If not verified: use a deterministic router (keyword/intent rules in Python)
that picks tools, then pass the results to the model. Prefer whichever is
simpler to test; the deterministic router is acceptable and easier to
evaluate. Record the choice in this doc.

Stage 2, answer synthesis: one model call. System prompt rules: use only the
supplied evidence; cite with `[Sn]`; quote numbers exactly as supplied (round to
4 decimals max, same as advisories); say "not available" when evidence is
missing; no advice/prediction/causal claims; 2-6 sentences.

All times in tool outputs are converted to UTC ISO-8601 with a trailing `Z`.

### 5.3 Retrieval corpus (no embeddings)
- Sources: `docs/FINDINGS.md`, `docs/ARCHITECTURE.md`, `docs/SCOPE.md`,
  `docs/DATA_SOURCES.md` (and this file's section 1 only if needed).
  Exclude `docs/SETUP.md` (operational secrets/paths).
- Build step: a script `genai/build_corpus.py` splits each file by markdown
  heading (`##`/`###`), keeps `{id, file, heading_path, text}`, and writes
  `backend/assistant/corpus.json`. This file MUST be committed under `backend/`:
  Render's root directory is `backend/`, so `docs/` does not exist at runtime
  (verified, Appendix A item 4). Re-run the script when docs
  change; add a check that fails CI/verification if `corpus.json` is stale
  (hash of source files stored in the JSON).
- Retrieval: lexical BM25 implemented in plain Python (about 40 lines, no new
  dependency), over chunk text plus heading. k=4. Return chunk text unmodified.
- Chunks longer than about 1,500 characters are split on paragraph boundaries
  with the heading path preserved.

### 5.4 Safety and abuse controls
- Input: max 500 chars; strip control characters; reject empty.
- Prompt-injection stance: retrieved text and tool outputs are *data*. The
  system prompt says instructions inside evidence must be ignored. Add test
  cases (6.2) with injected text in a stubbed evidence block.
- Rate limit per client IP (in-memory sliding window, tuned from the real Groq
  limits, 3.2) plus a global cap; return HTTP 429 with a friendly message. Note
  Render free tier may run one instance; in-memory is acceptable for a mini
  project and must be documented as a known limit.
- Cache identical (normalised question + data version) answers for 5 minutes
  in memory. Data version = `metadata.exported_at` plus the latest
  `recent_swap_events.observed_at`.
- Timeouts: Groq call 20s; whole request 30s; on failure return a graceful
  "assistant unavailable" response and still HTTP 200 or 503 consistently
  (pick one, document it). The rest of the dashboard must never depend on this
  endpoint.
- Never include the API key, raw upstream error bodies, or stack traces in
  responses or logs.

### 5.5 Post-hoc grounding check (the core of Part B)
After the model answers, `backend/assistant/grounding.py`:
1. Extract numbers from the answer (integers, decimals, percentages, and
   timestamps/dates normalised).
2. Build the allowed set from every number appearing in this turn's tool
   outputs and retrieved chunks, with tolerance rules: exact string match after
   normalisation, or equal after rounding to the displayed precision (4 dp).
3. Any answer number not in the allowed set is "ungrounded". Behaviour: retry
   once with a stricter instruction listing the offending numbers; if still
   ungrounded, return the answer with `grounding.checked=true`,
   `ungrounded_numbers=[...]`, and the UI shows a visible warning. Log counts
   (without user text) for the evaluation in Part B.
4. Small whole numbers that are list indices or ordinal words ("2 or 3",
   `[S1]` citation markers, the 0-100 scale, the 0-1 scale) are allow-listed via
   an explicit, tested list. Keep the list short and in one place.
5. Citations: every `[Sn]` in the answer must exist in `sources`; every claim
   sentence containing a number must carry at least one citation (best effort,
   reported as a metric, not a hard block).

### 5.6 Frontend
- New route `dashboard/app/assistant/page.tsx`, linked from the header like the
  existing "Evaluation" link in `dashboard/app/page.tsx`.
- Client component `dashboard/components/Assistant.tsx`: input, example
  question chips, message list, per-answer "Sources" disclosure, a visible
  banner "Descriptive only, not financial advice", and the grounding warning
  when `ungrounded_numbers` is non-empty. Match the existing styling and
  tokens (font-sans/font-mono, border-border, bg-surface, text-text-*); do not
  introduce a UI library.
- Proxy route `dashboard/app/api/assistant/route.ts` forwarding POST to
  `${RENDER_API_URL}/api/assistant/chat` with `cache: "no-store"`, same pattern
  as the existing proxies (the existing ones are GET; this one forwards a JSON
  body).
- v1 is non-streaming. Show a loading state and an error state. Respect
  `prefers-reduced-motion`. Keyboard accessible; `aria-live="polite"` on the
  answer region.
- Do not embed risk colours/severity styling; the assistant is explanatory.

### 5.7 Configuration
- New env var on Render: `GROQ_API_KEY` (secret). Optional
  `ASSISTANT_MODEL` (default = the verified model id). Add both to
  `docs/SETUP.md` and `.env.example` comments immediately. Setting a secret on
  Render is a manual step for the user (dashboard) or via the Render CLI only if
  the user approves; never echo the key.
- The batch advisory job keeps using the local `.env`; do not change its
  behaviour in this work except via Part B findings.

---

## 6. Part B: Faithfulness evaluation

Location: `genai/eval/` (new directory; add one line to the Conventions list in
`CLAUDE.md`). Runs offline from the dev machine, outputs a results JSON and a
short markdown report under `genai/eval/results/`. Not part of the request path.

### 6.1 Three measurements

B1. **Advisory faithfulness** (existing component, `current_risk_live.advisory`):
- Deterministic number check: every number in the advisory appears in the row's
  inputs at 4 dp (reuse `grounding.py` so one implementation serves both).
- Unsupported-claim scan: flag causal/predictive wording (`because`, `due to`,
  `caused`, `will`, `expected to`, `likely to`, `predict`, `forecast`); report
  rates. List the exact patterns in the script.
- Completeness: advisory exists (non-null) and ends with sentence punctuation
  (catches truncation).
- Run over many generations, not 4: regenerate advisories for synthetic rows
  built from real historical `current_risk`/live feature values (at least 100
  rows spanning calm, mid, and crisis scores) with each candidate model.
- Compare at least two model ids (include the current one). The candidate list
  must come from Groq's actual model list (3.6).

B2. **Chat QA accuracy** on a fixed question set (section 6.2).

B3. **Grounding-check effectiveness**: how often the post-hoc check catches an
injected wrong number (mutation test: take correct answers, change one number,
confirm detection; report detection rate).

### 6.2 Question set (chat)
- File `genai/eval/questions.json`, split into `dev` (used while tuning
  prompts) and `test` (frozen; touched only for the final report). Suggested 30
  dev + 40 test, written by hand.
- Each item: `{id, split, category, question, gold}`. `gold` values are
  produced by code from the live Supabase tables or from a committed snapshot of
  them, not typed by hand and not produced by an LLM. For doc questions, gold is
  the required fact plus the chunk id that contains it.
- Categories: `lookup` (current score of a pair), `comparison` (highest/lowest),
  `event_fact` (lead time, false alarms, peak score), `doc_grounded` (why UST
  has no baseline), `multi_hop` (compare USDC and UST lead time), `activity`
  (swap counts in a window), `refusal_advice`, `refusal_prediction`,
  `unanswerable` (asks for data not present, e.g. UST live price), `injection`
  (question or evidence containing "ignore previous instructions").
- Live questions drift as data changes. Freeze a snapshot
  (`genai/eval/snapshot/*.json`, exported once from the Render API) and run the
  tools against the snapshot in eval mode (dependency-inject the data source).
- Metrics: numeric exactness vs gold (tolerance: displayed precision), citation
  validity, refusal correctness, ungrounded-number rate, mean tool calls,
  latency. Report per category, with the denominator for every rate. Report
  results even when poor.

### 6.3 Reporting
`genai/eval/results/REPORT.md` includes: setup (model ids, date, snapshot hash),
tables, 5 worst failures with analysis, and an explicit limitations section.
Link it from `docs/FINDINGS.md` as a new section titled for what it measures;
do not overstate.

---

## 7. Part C: LLM-as-judge vs the rule-based score

### 7.1 Question
Given only anonymised feature windows, can an LLM label "elevated stress" as
well as the rule-based `risk_score` (threshold 7.18 from USDC calm data)?

### 7.2 Design
- Unit: a window of N consecutive hourly rows (N=24 default; try 12 and 48).
- Input to the model, per hour: `price_dev`, volume deviation, trade-count
  deviation, anomaly flag, cluster severity - i.e. the same *feature columns the
  rule score is built from* (see `spark/risk_scores_baseline.scala` and
  `docs/FINDINGS.md` "Rule-based baseline risk score" for the exact formula and
  weights; read both before building the extractor). Do NOT include the
  rule-based `risk_score` itself or its severity outputs in the prompt (that
  would let the model copy the answer).
- Anonymise to prevent pre-training leakage: remove pair names, dates, event
  names, absolute prices; express time as "hour 1..N"; scale features as
  z-scores. State in the report that leakage is reduced, not eliminated.
- Output: strict JSON `{"stress": "elevated"|"normal", "confidence": 0-1,
  "reason": "<one sentence>"}`; validate and reject malformed output (count it).
- Ground-truth label per window: the existing objective, price-based definition
  from `docs/FINDINGS.md` (a sustained >=2h hour with `|implied_price - 1| >=
  1%` or invalid price), NOT the rule-based score. A window is positive if it
  falls in the lead-up to or inside a sustained depeg (decide the exact
  horizon and write it down before looking at results).
- Compare four predictors on identical windows: (1) rule-based score >= 7.18,
  (2) the LLM judge, (3) a trivial baseline (`|price_dev|` threshold), (4)
  majority class. Metrics: precision, recall, F1, false-alarm rate per 100
  windows, and lead time in hours using the same definition as
  `evaluation_summary`.
- Evaluate on USDC_MAR2023 and UST_MAY2022 *separately*. UST has no RELIABLE
  calm baseline (`calm_caveat`), so UST windows are reported with that caveat
  and never pooled into a single headline number.
- Temperature 0 (or lowest allowed), fixed seed if supported, 3 repeats per
  window to report variance. Cache all responses to disk so a re-run does not
  re-bill/re-limit.
- Statistics: with two events, do not claim significance. Report counts and
  intervals (e.g. Wilson) and state the sample-size limit.

### 7.3 Deliverables
`genai/eval/judge_vs_rules.py`, cached responses under `genai/eval/cache/`
(gitignored if large), results in `genai/eval/results/judge_vs_rules.json` and a
section in `REPORT.md`. The outcome can be "LLM matches", "LLM worse", or
"inconclusive"; all are acceptable.

---

## 8. Phases and acceptance criteria

Phase 0 - Setup and verification (no feature code)
- Resolve every item in 3 (Unverified), recording answers in a new
  "Verification log" appendix of this file with date and evidence.
- Update `CLAUDE.md`: remove the stale "No GenAI" line, add `genai/` and
  `backend/assistant/` to Conventions.
- Acceptance: appendix filled in; user confirmed open decisions (section 10).

Phase 1 - Backend assistant (Part A core)
- `backend/assistant/` with tools, corpus builder + `corpus.json`, BM25,
  grounding check, endpoint, rate limit, cache.
- Unit tests (pytest, no network): tool outputs with a fake data source, BM25
  ranking on a tiny corpus, grounding check true/false positives, injection
  stub, rate limiter. Add `backend/requirements-dev.txt` for test deps; do not
  put test deps in `requirements.txt`.
- Acceptance: tests pass; local `uvicorn` run answers 5 sample questions
  against live data with citations; grounding flag works on a forced bad
  number.

Phase 2 - Frontend
- Page, component, proxy route, header link.
- Acceptance: `npm run lint`, `./node_modules/.bin/tsc --noEmit`, `npm run
  build` (needs `RENDER_API_URL`) pass; manual check of loading, error, refusal,
  429, and grounding-warning states at mobile and desktop widths.

Phase 3 - Evaluation (Part B)
- Harness, snapshot, question set, advisory regeneration experiment, report.
- Acceptance: `REPORT.md` generated by one command from a clean checkout;
  numbers reproducible from the snapshot.

Phase 4 - Judge experiment (Part C)
- Extractor, anonymiser, runner, comparison, report section.
- Acceptance: all four predictors computed on identical windows; per-event
  results; limitations written.

Phase 5 - Docs and release
- `docs/ARCHITECTURE.md` (new subsection under Application Layer),
  `docs/SETUP.md` (env vars, how to run eval), `docs/FINDINGS.md` (link to
  report), `docs/ROADMAP.md` if relevant.
- Set `GROQ_API_KEY` on Render (user-approved), deploy via normal merge to
  `main`, smoke-test the live endpoint, then the Vercel page.
- One PR per phase, never merged without the user's explicit go-ahead.

---

## 9. Verification commands (run before every PR)

```
# from repo root
python -m py_compile backend/main.py backend/assistant/*.py ingestion/generate_risk_advisories.py
(cd backend && pytest tests -q)    # after Phase 1 creates it
cd dashboard
npm run lint
./node_modules/.bin/tsc --noEmit
RENDER_API_URL=https://meridian-czv0.onrender.com npm run build
cd ..
git diff --check
```
Backend local run: `.venv/bin/python -m pip install -r backend/requirements.txt`
(or use a throwaway venv), set `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`,
`GROQ_API_KEY`, then, from inside `backend/`, `uvicorn main:app` (this is exactly how Render starts
the service; see Appendix A, item 4). Inside `backend/`, import the assistant
package as `from assistant import ...`, NOT `backend.assistant`, because
Render's root directory is `backend/`.

Live checks after deploy: `/health` returns ok; `POST /api/assistant/chat` with
a lookup question returns sources and `grounding.checked=true`; a prompt asking
for investment advice returns `refused=true`; 429 appears when the limit is
exceeded.

---

## 10. Decisions (resolved 2026-10-25 unless marked OPEN)

1. **Models.** Assistant: `openai/gpt-oss-20b` (already in use; confirmed
   Production and tool-capable, see Appendix A), configurable via
   `ASSISTANT_MODEL`. Evaluation compares it against `openai/gpt-oss-120b`
   (larger) and `llama-3.1-8b-instant` (smaller/faster); all three are listed
   as Production on Groq's models page. Note gpt-oss models do NOT support
   parallel tool calls, so tool calls are sequential (the 3-call cap in 5.2
   still holds).
2. **Rate limits.** Per-IP: about 5 questions/minute. Plus a global daily cap,
   set under the real free-tier daily limit and read from env
   (`ASSISTANT_DAILY_CAP`); friendly "assistant is resting" message when hit.
   The free-plan numbers are NOT public on the docs page (only Developer-plan
   numbers are), so the user must read them from the Groq console limits page
   and record them in Appendix A before the caps are finalised.
3. **Visibility.** The page is public but unlisted: no header link until just
   before the demo; enable by adding the link in `dashboard/app/page.tsx`.
4. **OPEN - course restrictions.** Needs the user to ask the other course's
   instructor whether retrieval + tool use + evaluation counts as GenAI and
   whether a specific technique/model is required. Blocks Phase 1.
5. **Advisory faithfulness on the dashboard.** Report only for now; revisit
   after Part B numbers exist.

---

## 11. Explicit exclusions

- No fine-tuning, no model training, no embeddings/vector DB (unless the user
  asks after seeing lexical retrieval results).
- No browser-side Groq calls; no key in the frontend.
- No write access from the assistant to any table; no model-written SQL.
- No trading/financial advice, no forecasts, no severity colours in the chat.
- No changes to the risk-score pipeline, frozen model artifacts, or Hive/Spark
  jobs. No re-fitting of any model.
- No new managed services beyond Groq (already used), Render, Supabase, Vercel.

---

## Appendix A: Verification log

Phase 0, 2026-10-25. Item numbers refer to section 3.

1. **Tool calling.** Groq's tool-use docs list `openai/gpt-oss-20b`,
   `openai/gpt-oss-120b`, `llama-3.3-70b-versatile` and `llama-3.1-8b-instant`
   as supporting local tool use. gpt-oss models: parallel tool calls NOT
   supported. Request shape: `tools=[{"type":"function","function":{"name",
   "description","parameters"(JSON Schema)}}]`; the model replies with
   `tool_calls` (`id`, `function.name`, `function.arguments` as a JSON string);
   append `{"role":"tool","tool_call_id":<id>,"name":..,"content":<string>}`
   and call again. Source: https://console.groq.com/docs/tool-use. Not yet
   smoke-tested against the live API with our key; do that first in Phase 1.
   Decision: model-driven tool calling is allowed; the deterministic router
   remains an acceptable fallback.
2. **Rate limits.** https://console.groq.com/docs/rate-limits only exposes
   Developer-plan values: gpt-oss-20b and gpt-oss-120b both 30 RPM, 1K RPD,
   8K TPM, 200K TPD. Free-plan values were not on the page. Action for the user:
   read the real numbers at the Groq console limits page and paste them here.
   Design consequence if free is similar: 8K TPM is small, so keep tool
   outputs compact (summaries, not 190 raw rows) and budget roughly 1.5-3K
   tokens per question.
3. **Embeddings.** Not needed (lexical BM25). Not checked; do not add.
4. **Render root directory.** `render services` shows service `Meridian`:
   `rootDir: backend/`, build `pip install -r requirements.txt`, start
   `uvicorn main:app --host 0.0.0.0 --port $PORT`, runtime python, no
   `render.yaml` in the repo. Consequence: only `backend/` is deployed;
   `docs/` is absent at runtime; imports are relative to `backend/`.
5. **Python version.** Exact version not read from Render. `backend/main.py`
   already uses `str | None` annotations and runs live, so >= 3.10 is
   confirmed in practice.
6. **Model ids.** https://console.groq.com/docs/models (Production):
   `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`,
   `openai/gpt-oss-20b`. `llama-3.1-8b-instant` does exist and is Production
   (the earlier worry was unfounded). Preview models exist but are not used.

Decisions: see section 10.

## Appendix B: Files this plan will touch or create

Existing: `backend/main.py` (mount the assistant router), `backend/requirements.txt`
(only if a new runtime dependency is unavoidable; none planned),
`ingestion/generate_risk_advisories.py` (only if Part B finds fixes),
`dashboard/app/page.tsx` (header link), `.env.example`, `CLAUDE.md`,
`docs/ARCHITECTURE.md`, `docs/SETUP.md`, `docs/FINDINGS.md`.

New: `backend/assistant/{__init__,tools,retrieval,grounding,prompts,router}.py`,
`backend/assistant/corpus.json`, `backend/tests/`, `genai/build_corpus.py`,
`genai/eval/*`, `dashboard/app/assistant/page.tsx`,
`dashboard/components/Assistant.tsx`, `dashboard/app/api/assistant/route.ts`.
