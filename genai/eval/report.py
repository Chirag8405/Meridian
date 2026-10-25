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
        note = f" **partial** (daily token quota; {errored} rate-limited rows excluded)" if len(recs) < 100 else ""
        out.append(f"| `{d['model']}`{note} | {len(recs)} ({bands}) | {pct(len(pres), len(recs))} | "
                   f"{pct(sum(r['score']['complete'] for r in pres), len(pres))} | "
                   f"{pct(sum(not r['score']['ungrounded_numbers'] for r in pres), len(pres))} | "
                   f"{pct(sum(not r['score']['causal_or_predictive'] for r in pres), len(pres))} | "
                   f"{pct(sum(r['score']['follows_2_or_3_sentences'] for r in pres), len(pres))} | "
                   f"{pct(sum(not r['score']['interpretive'] for r in pres), len(pres))} |")
    out += ["", "Models with different band mixes are not directly comparable (the partial run covers only the first rows, all calm).", ""]
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
    return ["### LLM judge vs rule-based score\n", "See judge_vs_rules.json.\n" if p.exists() else "Not run.\n"]


def main(argv=None) -> None:
    meta = json.loads((EVAL / "snapshot" / "_meta.json").read_text())
    out = ["# GenAI evaluation report\n",
           f"Generated from results in `genai/eval/results/`. Snapshot exported {meta['exported_at']}, "
           f"frozen activity clock {meta['now']}, sha256 `{meta['sha256'][:12]}`.\n",
           "## Part B: faithfulness\n"]
    out += chat_section("dev") + chat_section("test") + advisory_section() + mutation_section()
    out += ["## Part C: judge\n"] + judge_section()
    out += ["## Limitations\n",
            "- The dev split was used while tuning prompts and tools; only the test split is an honest estimate, and it is small (tens of questions), so differences of a few points are noise.",
            "- Gold answers come from a frozen snapshot, so live-data questions test the pipeline, not today's numbers.",
            "- The numeric grounding check is value-based: it catches invented numbers, not a correct number attached to the wrong claim (for example a comparison made from only some rows). The pass/fail scoring against gold is what measures that.",
            "- Advisory rows are synthetic (seeded, anchored on real ranges), not historical production rows.",
            "- Latencies include the harness's tokens/minute throttling (real single-user latency is a few seconds); token counts are real.",
            "- Chat QA was run only with the production model (gpt-oss-20b); its daily token quota was exhausted afterwards. The 20b advisory run is partial and test-040 was not re-run after a harness timeout (see plan Appendix C).",
            "- One model family at temperature 0.1, one run per question: variance across runs is not measured here.",
            ""]
    (RESULTS / "REPORT.md").write_text("\n".join(out))
    print("wrote genai/eval/results/REPORT.md")
