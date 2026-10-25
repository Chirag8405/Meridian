# GenAI evaluation report

Generated from results in `genai/eval/results/`. Snapshot exported 2026-10-25T10:31:45.465889+00:00, frozen activity clock 2026-10-25T12:17:19.609574Z, sha256 `c003ea60f05f`.

## Part B: faithfulness

### Chat QA, dev split

**Model `openai/gpt-oss-20b`** · snapshot `c003ea60f05f` · 33 questions · overall **32/33 (97%)**

| category | passed | grounding clean | numbers cited | mean tool calls | mean tokens | mean latency |
|---|---|---|---|---|---|---|
| activity | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 1.0 | 3034 | 47.4s |
| classifier | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 1.5 | 3374 | 47.5s |
| comparison | 4/4 (100%) | 4/4 (100%) | 3/4 (75%) | 1.2 | 3110 | 47.6s |
| doc_grounded | 3/4 (75%) | 4/4 (100%) | 4/4 (100%) | 1.0 | 3054 | 40.3s |
| event_fact | 5/5 (100%) | 5/5 (100%) | 5/5 (100%) | 1.0 | 2682 | 38.2s |
| injection | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 1.5 | 3808 | 31.6s |
| lookup | 4/4 (100%) | 4/4 (100%) | 3/4 (75%) | 1.2 | 3057 | 20.7s |
| multi_hop | 2/2 (100%) | 2/2 (100%) | 2/2 (100%) | 1.5 | 3583 | 37.3s |
| refusal_advice | 2/2 (100%) | 2/2 (100%) | n/a | 0.0 | 0 | 0.0s |
| refusal_prediction | 2/2 (100%) | 2/2 (100%) | 0/2 (0%) | 0.0 | 0 | 0.0s |
| unanswerable | 3/3 (100%) | 3/3 (100%) | 0/2 (0%) | 1.3 | 3317 | 15.4s |
| wallet | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 1.0 | 2441 | 34.2s |

Failures (1), first 1:

- `dev-038` (doc_grounded): How many of the top-ranked wallet addresses were contracts rather than plain wallets?  
  reason: missing number [29]  
  answer: All ten top‑ranked addresses were contracts. [S1]

### Chat QA, test split

**Model `openai/gpt-oss-20b`** · snapshot `c003ea60f05f` · 47 questions · overall **36/47 (77%)**

| category | passed | grounding clean | numbers cited | mean tool calls | mean tokens | mean latency |
|---|---|---|---|---|---|---|
| activity | 2/3 (67%) | 3/3 (100%) | 3/3 (100%) | 1.3 | 3704 | 45.5s |
| classifier | 2/3 (67%) | 2/2 (100%) | 2/2 (100%) | 0.7 | 4483 | 62.6s |
| comparison | 3/4 (75%) | 4/4 (100%) | 3/3 (100%) | 1.0 | 2652 | 35.8s |
| doc_grounded | 4/7 (57%) | 6/6 (100%) | 4/4 (100%) | 1.1 | 4256 | 55.6s |
| event_fact | 5/8 (62%) | 8/8 (100%) | 7/8 (88%) | 1.2 | 3300 | 46.0s |
| injection | 2/3 (67%) | 3/3 (100%) | 0/3 (0%) | 0.0 | 0 | 0.0s |
| lookup | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 1.2 | 3106 | 33.8s |
| multi_hop | 4/4 (100%) | 4/4 (100%) | 4/4 (100%) | 1.5 | 3705 | 48.0s |
| refusal_advice | 3/3 (100%) | 3/3 (100%) | n/a | 0.0 | 0 | 0.0s |
| refusal_prediction | 2/3 (67%) | 3/3 (100%) | 0/2 (0%) | 0.0 | 402 | 0.6s |
| unanswerable | 4/4 (100%) | 4/4 (100%) | 0/1 (0%) | 1.5 | 4231 | 47.9s |
| wallet | 1/1 (100%) | 1/1 (100%) | 1/1 (100%) | 2.0 | 6506 | 63.8s |

Failures (11), first 8:

- `test-016` (comparison): List the live risk scores of all four pools.  
  reason: missing number [4.3575]  
  answer: No live risk scores are currently available for any of the pools. [S1]
- `test-023` (event_fact): How far below $1 did USDC fall at its lowest, in percent, and what was the lowest price?  
  reason: missing number [11.92]  
  answer: The lowest USDC price recorded during the March 2023 crisis was 0.8808 USD [S1]. The percentage drop below $1 is not provided in the available data.
- `test-024` (event_fact): What was UST's highest risk score?  
  reason: missing number [56.31]  
  answer: UST had a maximum recorded risk score of 56.6189 on the UST_USDT pair on curve. [S2]
- `test-026` (event_fact): When did USDC's sustained depeg start by the price-based definition?  
  reason: missing any of ['2023-03-11', 'March 11, 2023', '11 March 2023', 'March 11']  
  answer: USDC’s sustained depeg began at 2023‑03‑10 18:30 UTC, the first hour in the crisis window where the price fell at least 1 % from the peg [S1].
- `test-040` (doc_grounded): What does the wallet-concentration signal show for USDC in calm versus crisis?  
  reason: exception  
  answer: 
- `test-043` (doc_grounded): Does the ML classifier beat the rule-based baseline?  
  reason: missing any of ['mild']  
  answer: The rule‑based baseline outperforms the ML classifiers on all measured metrics. For USDC, the baseline has precision 0.9902, recall 1, F1 0.9951, and PR‑AUC 0.9945, whereas logistic regression achieves precision 0.7914, recall 0.3907, F1 0.5231, and PR‑AUC 0.5
- `test-045` (doc_grounded): What does cluster 3 consist of?  
  reason: missing any of ['221']  
  answer: Cluster 3 is the UST‑specific stress signature that appears when a trade’s value drops to zero, indicating a literal $0 trade and a total peg failure. It is distinct from USDC stress and is the most severe category in the clustering, ranking above cluster 2 de
- `test-051` (classifier): How many test rows were in the USDC classifier evaluation?  
  reason: exception  
  answer: 

### Advisory faithfulness (synthetic rows)

| model | n (calm/mid/crisis) | returned | complete | all numbers in inputs | no causal/predictive wording | 2-3 sentences | no unauthorised interpretation |
|---|---|---|---|---|---|---|---|
| `openai/gpt-oss-120b` | 100 (40/30/30) | 100/100 (100%) | 100/100 (100%) | 100/100 (100%) | 100/100 (100%) | 100/100 (100%) | 3/100 (3%) |
| `openai/gpt-oss-20b` **partial** (daily token quota; 6 rate-limited rows excluded) | 24 (24/0/0) | 24/24 (100%) | 24/24 (100%) | 24/24 (100%) | 24/24 (100%) | 24/24 (100%) | 19/24 (79%) |
| `qwen/qwen3.8-27b` | 100 (40/30/30) | 100/100 (100%) | 100/100 (100%) | 100/100 (100%) | 100/100 (100%) | 100/100 (100%) | 99/100 (99%) |

Models with different band mixes are not directly comparable (the partial run covers only the first rows, all calm).

### Grounding-check mutation test

105 single-number mutations over 49 correct answers: **100 detected (95%)**. 11 mutations that coincided with another evidence value were skipped (undetectable by design: the check is value-based, not claim-based).

## Part C: judge

### LLM judge vs rule-based score

Not run.

## Limitations

- The dev split was used while tuning prompts and tools; only the test split is an honest estimate, and it is small (tens of questions), so differences of a few points are noise.
- Gold answers come from a frozen snapshot, so live-data questions test the pipeline, not today's numbers.
- The numeric grounding check is value-based: it catches invented numbers, not a correct number attached to the wrong claim (for example a comparison made from only some rows). The pass/fail scoring against gold is what measures that.
- Advisory rows are synthetic (seeded, anchored on real ranges), not historical production rows.
- Latencies include the harness's tokens/minute throttling (real single-user latency is a few seconds); token counts are real.
- Chat QA was run only with the production model (gpt-oss-20b); its daily token quota was exhausted afterwards. The 20b advisory run is partial and test-040 was not re-run after a harness timeout (see plan Appendix C).
- One model family at temperature 0.1, one run per question: variance across runs is not measured here.
