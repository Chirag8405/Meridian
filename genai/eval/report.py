"""Assemble results/REPORT.md from whatever results exist.

    python genai/eval/run.py report
Every rate is printed with its denominator; absent parts are marked "not run".
"""

import json
from collections import defaultdict
from statistics import mean

from common import EVAL, RESULTS


def pct(k, n):
    return f"{k}/{n} ({100 * k / n:.0f}%)" if n else "n/a"


def chat_section(split: str) -> list[str]:
    files = sorted(RESULTS.glob(f"chat_*_{split}.json"))
    if not files:
        return [f"### Chat QA, {split} split\n", "Not run.\n"]
    out = [f"### Chat QA, {split} split\n"]
    for f in files:
        d = json.loads(f.read_text())
        recs = d["records"]
        out.append(f"**Model `{d['model']}`** · snapshot `{d['snapshot_sha256'][:12]}` · {len(recs)} questions · "
                   f"overall **{pct(sum(r['passed'] for r in recs), len(recs))}**\n")
        by = defaultdict(list)
        for r in recs:
            by[r["category"]].append(r)
        out += ["| category | passed | grounding clean | numbers cited | mean tool calls | mean tokens | mean latency |",
                "|---|---|---|---|---|---|---|"]
        for cat in sorted(by):
            rs = by[cat]
            fl = [r["flags"] for r in rs if r.get("flags")]
            num = [x for x in fl if x["has_numbers"]]
            out.append(f"| {cat} | {pct(sum(r['passed'] for r in rs), len(rs))} | "
                       f"{pct(sum(x['grounding_clean'] for x in fl), len(fl))} | "
                       f"{pct(sum(x['cited'] for x in num), len(num))} | "
                       f"{mean(r['tool_calls'] for r in rs):.1f} | {mean(r['tokens'] for r in rs):.0f} | "
                       f"{mean(r['latency_s'] for r in rs):.1f}s |")
        out.append("")
        fails = [r for r in recs if not r["passed"]]
        if fails:
            out.append(f"Failures ({len(fails)}), first {min(8, len(fails))}:\n")
            for r in fails[:8]:
                out.append(f"- `{r['id']}` ({r['category']}): {r['question']}  \n  reason: {r['reason'] or r.get('error')}  \n"
                           f"  answer: {r['answer'][:260].replace(chr(10), ' ')}")
            out.append("")
    return out


def before_after_section() -> list[str]:
    old_path = RESULTS / "before-fixes_chat_openai_gpt-oss-20b_test.json"
    new_path = RESULTS / "chat_openai_gpt-oss-20b_test.json"
    if not (old_path.exists() and new_path.exists()):
        return []
    old = {r["id"]: r for r in json.loads(old_path.read_text())["records"]}
    new = {r["id"]: r for r in json.loads(new_path.read_text())["records"]}
    gained = [i for i in new if new[i]["passed"] and not old[i]["passed"]]
    lost = [i for i in new if not new[i]["passed"] and old[i]["passed"]]
    still = [i for i in new if not new[i]["passed"] and not old[i]["passed"]]
    out = ["### Test split before vs after the post-evaluation fixes\n",
           f"First run (before the fixes): **{sum(r['passed'] for r in old.values())}/{len(old)}**. Re-run after them "
           f"(same questions, same snapshot): **{sum(r['passed'] for r in new.values())}/{len(new)}**. "
           f"Newly passing: {', '.join(gained) or 'none'}. Newly failing: {', '.join(lost) or 'none'}. "
           f"Failing in both: {', '.join(still) or 'none'}.\n",
           "How much of that is the fixes, and how much is run-to-run noise: only `test-066` (\"Is DAI going to collapse?\", "
           "the prediction-refusal pattern) and `test-040` (a harness timeout in the first run, not a product failure) have a "
           "direct cause. The others changed with no code change aimed at them, so treat the 36 to 40 move as an upper "
           "bound on improvement, not a measured effect. `test-051` failed in the first run with a Groq HTTP 400 and "
           "in both re-runs with a rate limit (HTTP 429 / 300 s timeout from throttling), so it is unresolved.\n"]
    return out


def advisory_section() -> list[str]:
    from advisory_eval import score_advisory  # rescored from stored text, so scoring fixes need no API calls

    files = sorted(RESULTS.glob("advisory_*.json"))
    out = ["### Advisory faithfulness (synthetic rows)\n"]
    if not files:
        return out + ["Not run.\n"]
    out += ["| model | n (calm/mid/crisis) | returned | complete | all numbers in inputs | no causal/predictive wording | 2-3 sentences | no unauthorised interpretation |",
            "|---|---|---|---|---|---|---|---|"]
    for f in files:
        d = json.loads(f.read_text())
        allrecs = d["records"]
        errored = sum(1 for r in allrecs if r.get("error"))  # rate-limited calls: infrastructure, not model behaviour
        recs = [r for r in allrecs if not r.get("error")]
        for r in recs:
            r["score"] = score_advisory(r["row"], r["advisory"])
        pres = [r for r in recs if r["score"].get("present")]
        bands = "/".join(str(sum(1 for r in recs if r["band"] == b)) for b in ("calm", "mid", "crisis"))
        note = f" ({errored} row(s) rate-limited by Groq on every retry, excluded)" if errored else ""
        out.append(f"| `{d['model']}`{note} | {len(recs)} ({bands}) | {pct(len(pres), len(recs))} | "
                   f"{pct(sum(r['score']['complete'] for r in pres), len(pres))} | "
                   f"{pct(sum(not r['score']['ungrounded_numbers'] for r in pres), len(pres))} | "
                   f"{pct(sum(not r['score']['causal_or_predictive'] for r in pres), len(pres))} | "
                   f"{pct(sum(r['score']['follows_2_or_3_sentences'] for r in pres), len(pres))} | "
                   f"{pct(sum(not r['score']['interpretive'] for r in pres), len(pres))} |")
    out += ["", "Rows are synthetic (seeded, same rows for every model). The last column is a heuristic word list "
            "(suggest/indicate/reflect/imply/signal, or a level word such as moderate/high/low/elevated before risk/stress/"
            "concentration/deviation): a verdict the prompt gives the model no thresholds for.", ""]
    return out


def mutation_section() -> list[str]:
    p = RESULTS / "mutation.json"
    if not p.exists():
        return ["### Grounding-check mutation test\n", "Not run.\n"]
    m = json.loads(p.read_text())
    return ["### Grounding-check mutation test\n",
            f"{m['mutations']} single-number mutations over {m['answers_used']} correct answers: "
            f"**{m['detected']} detected ({100 * (m['detection_rate'] or 0):.0f}%)**. "
            f"{m['collisions_skipped']} mutations that coincided with another evidence value were skipped "
            "(undetectable by design: the check is value-based, not claim-based).\n"]


def judge_section() -> list[str]:
    p = RESULTS / "judge_vs_rules.json"
    if not p.exists():
        return ["### LLM judge vs rule-based score\n", "Not run.\n"]
    d = json.loads(p.read_text())
    out = ["### LLM judge vs rule-based score\n",
           "Question: for a 24-hour window of raw hourly behaviour (no names, dates, absolute prices or scores), is a "
           "sustained depeg (price at least 1% off $1, or no valid price, for 2+ consecutive hours) underway or about to "
           "begin within 72 hours? Label is price-based and never uses the risk score. Details and design: "
           "`genai/eval/judge_windows.py`, plan section 7.\n"]
    for event, ev in d["events"].items():
        out.append(f"**{event}**: {ev['windows_total']} windows ({ev['positives_total']} positive); the LLM saw a sampled "
                   f"subset of {ev['subset_total']} ({ev['subset_positives']} positive). Rows marked *subset* are on that "
                   "subset (class-balanced by design, so its precision is not comparable to the all-windows precision).\n")
        out += ["| predictor | windows | precision | recall (95% CI) | false-alarm rate (95% CI) |", "|---|---|---|---|---|"]
        for name, m in ev["predictors"].items():
            for scope in ("all_windows", "llm_subset"):
                if scope not in m:
                    continue
                k = m[scope]
                fmt = lambda v: "n/a" if v is None else f"{v:.2f}"
                ci = lambda c: "" if not c else f" [{c[0]:.2f}, {c[1]:.2f}]"
                label = name + (" (subset)" if scope == "llm_subset" and not name.startswith("llm:") else "")
                extra = f", {m['invalid_replies']} unparseable" if m.get("invalid_replies") else ""
                out.append(f"| {label} | {k['n']}{extra} | {fmt(k['precision'])} | {fmt(k['recall'])}{ci(k['recall_ci95'])} | "
                           f"{fmt(k['false_alarm_rate'])}{ci(k['false_alarm_ci95'])} |")
        out.append("")
    out += ["Caveats:"] + [f"- {c}" for c in d["caveats"]] + [""]
    return out


def main(argv=None) -> None:
    meta = json.loads((EVAL / "snapshot" / "_meta.json").read_text())
    out = ["# GenAI evaluation report\n",
           f"Generated from results in `genai/eval/results/`. Snapshot exported {meta['exported_at']}, "
           f"frozen activity clock {meta['now']}, sha256 `{meta['sha256'][:12]}`.\n",
           "## Part B: faithfulness\n"]
    out += chat_section("dev") + chat_section("test") + before_after_section() + advisory_section() + mutation_section()
    out += ["## Part C: judge\n"] + judge_section()
    out += ["## Limitations\n",
            "- The dev split was used while tuning prompts and tools; only the test split is an honest estimate, and it is small (tens of questions), so differences of a few points are noise.",
            "- Gold answers come from a frozen snapshot, so live-data questions test the pipeline, not today's numbers.",
            "- The numeric grounding check is value-based: it catches invented numbers, not a correct number attached to the wrong claim (for example a comparison made from only some rows). The pass/fail scoring against gold is what measures that.",
            "- Advisory rows are synthetic (seeded, anchored on real ranges), not historical production rows.",
            "- Latencies include the harness's tokens/minute throttling (real single-user latency is a few seconds); token counts are real.",
            "- Chat QA was run only with the production model (gpt-oss-20b). Single runs: question outcomes change between runs of the same code (the before/after test comparison below includes that noise).",
            "- One model family at temperature 0.1, one run per question: variance across runs is not measured here.",
            ""]
    (RESULTS / "REPORT.md").write_text("\n".join(out))
    print("wrote genai/eval/results/REPORT.md")
