"""Run the question set through the real assistant pipeline against the frozen snapshot.

    python genai/eval/run.py chat --split dev            # tuning set
    python genai/eval/run.py chat --split test           # frozen: final report only
    options: --model ID  --limit N  --ids a,b  --force

Resumable: finished question ids are kept in results/chat_<model>_<split>.json.
Costs real Groq quota (about 2-3 requests and ~2.5K tokens per question).
"""

import argparse
import asyncio
import json
import time

from common import RESULTS, ROOT, EVAL, PacedLLM, SnapshotSource, load_env, snapshot_now
from score import check, quality_flags


def run_one(q, src, index, llm, settings, tools_mod, answer_question):
    llm.reset()
    t0 = time.time()
    try:
        out = asyncio.run(asyncio.wait_for(answer_question(q["question"], [], src, index, llm, settings), 300))
        err = None
    except Exception as exc:  # recorded, scored as a failure
        out, err = None, f"{type(exc).__name__}: {exc}"
    rec = {"id": q["id"], "split": q["split"], "category": q["category"], "question": q["question"],
           "latency_s": round(time.time() - t0, 2), "llm_calls": llm.calls, "tokens": llm.tokens}
    if out is None:
        rec.update(error=err, passed=False, reason="exception", answer="", grounding=None, tool_calls=0)
        return rec
    passed, why = check(q["gold"], out, q["question"])
    tool_results = [m["content"] for m in llm.last_messages if m.get("role") == "tool"]
    rec.update(answer=out["answer"], sources=out["sources"], refused=out["refused"], grounding=out["grounding"],
               tool_calls=out["tool_calls"], passed=passed, reason=why, flags=quality_flags(out),
               tool_results=tool_results)
    return rec


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--model")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)

    import os
    env = load_env()
    os.environ["GROQ_API_KEY"] = env.get("GROQ_API_KEY", "")
    if a.model:
        os.environ["ASSISTANT_MODEL"] = a.model
    from assistant import tools
    from assistant.chat import answer_question
    from assistant.config import load_settings
    from assistant.llm import GroqClient
    from assistant.retrieval import load_index

    settings = load_settings()
    if not settings.api_key:
        raise SystemExit("GROQ_API_KEY missing from .env")
    tools.now = snapshot_now  # frozen "now" so activity answers are reproducible
    qs = json.loads((EVAL / "questions.json").read_text())["questions"]
    qs = [q for q in qs if a.split == "all" or q["split"] == a.split]
    if a.ids:
        qs = [q for q in qs if q["id"] in a.ids.split(",")]
    if a.limit:
        qs = qs[: a.limit]

    safe = settings.model.replace("/", "_")
    path = RESULTS / f"chat_{safe}_{a.split}.json"
    done = {} if a.force or not path.exists() else {r["id"]: r for r in json.loads(path.read_text())["records"]}
    src, index, llm = SnapshotSource(), load_index(), PacedLLM(GroqClient(settings))
    meta = json.loads((EVAL / "snapshot" / "_meta.json").read_text())
    for n, q in enumerate(qs, 1):
        if q["id"] in done:
            continue
        rec = run_one(q, src, index, llm, settings, tools, answer_question)
        done[q["id"]] = rec
        mark = "PASS" if rec["passed"] else f"FAIL ({rec['reason']})"
        print(f"[{n}/{len(qs)}] {q['id']} {q['category']:<18} {mark}  {rec['latency_s']}s {rec['tokens']}tok", flush=True)
        path.write_text(json.dumps({"model": settings.model, "split": a.split, "snapshot_sha256": meta["sha256"],
                                    "records": list(done.values())}, indent=1) + "\n")
    recs = list(done.values())
    print(f"\n{sum(r['passed'] for r in recs)}/{len(recs)} passed -> {path.relative_to(ROOT)}")
