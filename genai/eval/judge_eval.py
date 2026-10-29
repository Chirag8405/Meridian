"""Part C, step 2: run the LLM judge on the sampled windows and compare with the rule-based score.

    python genai/eval/run.py judge --model openai/gpt-oss-120b [--limit N] [--force]
    python genai/eval/run.py judge --score          # (re)score only, no API calls

Cost: ~1.2K tokens per window, 60 positive + 60 negative per event at most; one request each.
Results are cached per model in results/judge_<model>.json (resumable). Output:
results/judge_vs_rules.json. Read docs/GENAI_ASSISTANT_PLAN.md section 7 and judge_windows.py first.
"""

import argparse
import asyncio
import json
import math
import os
import re

from common import RESULTS, PacedLLM, load_env
from judge_windows import JUDGE

SYSTEM = ("You are a market-surveillance analyst for stablecoins. Use only the table you are given. "
          "Answer with a single JSON object and nothing else.")


def prompt_for(window: dict) -> str:
    lines = ["hour | price_dev_pct | volume_vs_median | trades_vs_median | anomaly | price_valid"]
    for f in window["features"]:
        def fmt(v):
            return "n/a" if v is None else str(v)
        lines.append(f"{f['hour']} | {fmt(f['price_deviation_pct'])} | {fmt(f['volume_vs_window_median'])} | "
                     f"{fmt(f['trades_vs_window_median'])} | {fmt(f['anomaly_flag'])} | {fmt(f['price_valid'])}")
    return (
        "Below are the last 24 hourly readings (hour 0 is the most recent) for one stablecoin trading pool. "
        "price_dev_pct is the price's deviation from its $1 peg in percent; volume and trades are ratios to this "
        "window's own median; anomaly is a data-quality flag.\n\n" + "\n".join(lines) + "\n\n"
        "Question: is a SUSTAINED depeg (price at least 1% away from $1, or no valid price, for at least 2 "
        "consecutive hours) already underway or likely to begin within the next 72 hours?\n"
        'Reply as JSON: {"depeg_risk": "high" or "low", "confidence": a number from 0 to 1, '
        '"reason": "one short sentence"}'
    )


def parse_reply(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    if d.get("depeg_risk") not in ("high", "low"):
        return None
    return d


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0, c - h), 3), round(min(1, c + h), 3)]


def metrics(pairs: list[tuple[int, int]]) -> dict:
    """pairs of (label, predicted)."""
    tp = sum(1 for y, p in pairs if y and p)
    fp = sum(1 for y, p in pairs if not y and p)
    fn = sum(1 for y, p in pairs if y and not p)
    tn = sum(1 for y, p in pairs if not y and not p)
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else (0.0 if prec is not None and rec is not None else None)
    return {"n": len(pairs), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": None if prec is None else round(prec, 3), "recall": None if rec is None else round(rec, 3),
            "f1": None if f1 is None else round(f1, 3),
            "false_alarm_rate": round(fp / (fp + tn), 3) if fp + tn else None,
            "recall_ci95": wilson(tp, tp + fn), "false_alarm_ci95": wilson(fp, fp + tn)}


def score(all_windows: list[dict], llm: dict[str, dict]) -> dict:
    out = {"definition": "see genai/eval/judge_windows.py docstring", "events": {}}
    for event in ("USDC", "UST"):
        ws = [w for w in all_windows if w["event"] == event]
        sub = [w for w in ws if w["llm_subset"]]
        ev = {"windows_total": len(ws), "positives_total": sum(w["label"] for w in ws),
              "subset_total": len(sub), "subset_positives": sum(w["label"] for w in sub),
              "predictors": {}}
        for name in ("rule", "price_1pct", "price_05pct", "majority"):
            ev["predictors"][name] = {
                "all_windows": metrics([(w["label"], int(w[name])) for w in ws]),
                "llm_subset": metrics([(w["label"], int(w[name])) for w in sub]),
            }
        for model, recs in llm.items():
            pairs, invalid = [], 0
            for w in sub:
                r = recs.get(w["id"])
                if r is None:
                    continue
                if r.get("parsed") is None:
                    invalid += 1
                    continue
                pairs.append((w["label"], int(r["parsed"]["depeg_risk"] == "high")))
            ev["predictors"][f"llm:{model}"] = {"llm_subset": metrics(pairs), "invalid_replies": invalid,
                                                "windows_answered": len(pairs) + invalid}
        out["events"][event] = ev
    out["caveats"] = [
        "UST has no genuinely calm baseline (docs/FINDINGS.md); its negatives are few and its series starts already destabilised. UST is never pooled with USDC.",
        "Two events, one pair each: counts and 95% Wilson intervals are reported; no significance claim is made.",
        "The rule score uses baseline statistics and cluster/wallet signals the judge does not see; the judge sees only raw hourly behaviour.",
        "Pre-training leakage is reduced (no dates, names, absolute prices) but not eliminated: the shape of a famous depeg may still be recognised.",
        "One run per window at temperature 0.1 (the assistant client's fixed setting); run-to-run variance is not measured.",
    ]
    return out


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args(argv)
    windows = json.loads((JUDGE / "windows.json").read_text())["windows"]
    sub = [w for w in windows if w["llm_subset"]]

    if a.model and not a.score:
        os.environ["GROQ_API_KEY"] = load_env().get("GROQ_API_KEY", "")
        os.environ["ASSISTANT_MODEL"] = a.model
        from assistant.config import load_settings
        from assistant.llm import GroqClient

        settings = load_settings()
        if not settings.api_key:
            raise SystemExit("GROQ_API_KEY missing from .env")
        llm = PacedLLM(GroqClient(settings), est_call_tokens=1500)
        path = RESULTS / f"judge_{a.model.replace('/', '_')}.json"
        done = {} if a.force or not path.exists() else json.loads(path.read_text())["records"]
        todo = [w for w in sub if w["id"] not in done]
        if a.limit:
            todo = todo[: a.limit]
        for n, w in enumerate(todo, 1):
            llm.reset()
            try:
                out = asyncio.run(llm.complete([{"role": "system", "content": SYSTEM},
                                                {"role": "user", "content": prompt_for(w)}]))
                text, finish = out["message"].get("content") or "", out.get("finish_reason")
                err = None
            except Exception as exc:
                text, finish, err = "", None, f"{type(exc).__name__}: {exc}"
            done[w["id"]] = {"parsed": parse_reply(text) if finish != "length" else None, "raw": text[:400],
                             "finish": finish, "error": err, "tokens": llm.tokens}
            print(f"[{n}/{len(todo)}] {w['id']} label={w['label']} -> {done[w['id']]['parsed']}", flush=True)
            path.write_text(json.dumps({"model": a.model, "records": done}, indent=1) + "\n")

    llm_results = {}
    for f in sorted(RESULTS.glob("judge_*.json")):
        if f.name == "judge_vs_rules.json":
            continue
        d = json.loads(f.read_text())
        llm_results[d["model"]] = d["records"]
    result = score(windows, llm_results)
    (RESULTS / "judge_vs_rules.json").write_text(json.dumps(result, indent=1) + "\n")
    for event, ev in result["events"].items():
        print(f"\n{event}: {ev['windows_total']} windows ({ev['positives_total']} positive); LLM subset {ev['subset_total']}")
        for name, m in ev["predictors"].items():
            k = m.get("all_windows") or m["llm_subset"]
            print(f"  {name:<32} P={k['precision']} R={k['recall']} F1={k['f1']} FAR={k['false_alarm_rate']} (n={k['n']})")
