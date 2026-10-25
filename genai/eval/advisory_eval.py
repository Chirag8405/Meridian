"""B1: faithfulness of the production advisory generator, across models.

    python genai/eval/run.py advisory [--n 100] [--models a,b,c]

Uses ingestion/generate_risk_advisories.py itself (its prompt_for/generate),
swapping only its MODEL constant, over SYNTHETIC rows. The rows are synthetic
because historical feature rows live in Hive (stress_clusters has no live rows)
and are not exposed to the dashboard; ranges are anchored on real values:
calm score 4.37 +/- 1.4 and elevated threshold 7.18 (evaluation_summary), USDC
peak 81.18, UST peak 56.31, cluster severities 0.05/0.5/0.85/1.0 and the USDC
calm wallet-concentration severity used in production. Seeded, so identical
rows are shown to every model. Reported as synthetic in the report.
"""

import argparse
import importlib.util
import json
import random
import re
import time

from common import RESULTS, ROOT, load_env
from assistant import grounding

DEFAULT_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.8-27b"]
SEVERITY = {0: 0.05, 1: 0.5, 2: 0.85, 3: 1.0}
WALLET = 0.12830815594836484
CAUSAL = re.compile(
    r"\b(because|due to|caused|causing|as a result|owing to|driven by|thanks to|will|would|expected to|"
    r"likely to|likely|predict\w*|forecast\w*|should|could|may|might|suggests? that)\b", re.I)


# Interpretation the prompt did not authorise: verdicts and risk labels are not derivable from
# the supplied numbers (the thresholds live in the project docs, not in the prompt).
INTERPRETIVE = re.compile(
    r"\b(suggest\w*|indicat\w*|reflect\w*|impl(y|ies|ying)|signal\w*|reveal\w*|"
    r"(low|moderate|moderately|high|highly|elevated|severe|calm|critical|dangerous|safe|stable|unstable|concerning|significant|substantial|minimal|negligible)"
    r"(?= (level|risk|stress|concentration|deviation|volatility|severity)))\b", re.I)


def synth_rows(n: int, seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        band = "calm" if i < 0.4 * n else "mid" if i < 0.7 * n else "crisis"
        if band == "calm":
            score, dev, cl = min(7.1, max(2.0, rng.gauss(4.37, 1.4))), rng.gauss(0, 0.6), 0
        elif band == "mid":
            score, dev, cl = rng.uniform(7.2, 25), rng.choice([-1, 1]) * rng.uniform(1.5, 4), rng.choice([0, 1])
        else:
            score, dev, cl = rng.uniform(25, 82), rng.choice([-1, 1]) * rng.uniform(4, 15), rng.choice([1, 2, 3])
        rows.append({"pair": "USDC_USDT", "project": "curve", "band": band, "risk_score": score, "price_dev": dev,
                     "cluster_id": cl, "cluster_severity": SEVERITY[cl], "wallet_concentration_severity": WALLET})
    return rows


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_adv", ROOT / "ingestion" / "generate_risk_advisories.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def score_advisory(row: dict, text: str | None) -> dict:
    if not text:
        return {"present": False}
    inputs = [row["risk_score"], row["price_dev"], row["cluster_id"], row["cluster_severity"],
              row["wallet_concentration_severity"]]
    # The prompt shows inputs at 4 dp, so evidence is the 4 dp rendering plus the row's pair/DEX text.
    pool = grounding.evidence_numbers([float(f"{v:.4f}") if isinstance(v, float) else v for v in inputs],
                                      f"{row['pair']} {row['project']}")
    bad = grounding.ungrounded_numbers(text, pool)
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    return {
        "present": True,
        "complete": text.rstrip()[-1] in ".!?",
        "ungrounded_numbers": bad,
        "causal_or_predictive": sorted({m.group(0).lower() for m in CAUSAL.finditer(text)}),
        "interpretive": sorted({m.group(0).lower() for m in INTERPRETIVE.finditer(text)}),
        "sentences": len(sentences),
        "follows_2_or_3_sentences": 2 <= len(sentences) <= 3,
    }


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--sleep", type=float, default=9.0)  # the 8K tokens/min limit allows about 6 of these/min
    a = ap.parse_args(argv)
    key = load_env().get("GROQ_API_KEY", "")
    if not key:
        raise SystemExit("GROQ_API_KEY missing from .env")
    gen = load_generator()
    rows = synth_rows(a.n)
    for model in a.models.split(","):
        gen.MODEL = model
        safe = model.replace("/", "_")
        path = RESULTS / f"advisory_{safe}.json"
        done = ({r["i"]: r for r in json.loads(path.read_text())["records"] if not r["error"]}
                if path.exists() else {})  # errored rows (rate limits) are retried on resume
        for i, row in enumerate(rows):
            if i in done:
                continue
            text, err = None, None
            for attempt in range(4):
                try:
                    text = gen.generate(row, key)
                    break
                except Exception as exc:  # network / 429: back off, record the last error
                    err = type(exc).__name__ + (f" {exc.response.status_code}" if hasattr(exc, "response") and exc.response is not None else "")
                    time.sleep(15 * (attempt + 1))
            done[i] = {"i": i, "band": row["band"], "row": row, "advisory": text, "error": err if text is None else None,
                       "score": score_advisory(row, text)}
            time.sleep(a.sleep)
            if i % 10 == 9:
                path.write_text(json.dumps({"model": model, "synthetic_rows": True, "records": list(done.values())}, indent=1) + "\n")
                print(f"{model}: {len(done)}/{len(rows)}", flush=True)
        path.write_text(json.dumps({"model": model, "synthetic_rows": True, "records": list(done.values())}, indent=1) + "\n")
        ok = sum(1 for r in done.values() if r["score"].get("present") and not r["score"]["ungrounded_numbers"])
        print(f"{model}: done, {ok}/{len(done)} faithful-and-present")
