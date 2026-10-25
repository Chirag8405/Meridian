"""B3: does the numeric grounding check catch a wrong number?

    python genai/eval/run.py mutation

Takes every chat answer that passed with clean grounding, changes ONE number
at a time to a different value, and re-runs the check against that answer's
original evidence. Pure and offline (no API calls). A mutation that lands on a
value that is itself in the evidence is a "collision": undetectable by design
(the check is value-based), reported separately instead of as a miss.
"""

import json
import re
from decimal import Decimal

from common import RESULTS
from assistant import grounding


def mutate(written: str) -> str:
    """Different value, same number of decimals."""
    clean = written.replace(",", "").rstrip("%")
    if "." in clean:
        places = len(clean.split(".")[1])
        return f"{Decimal(clean) + Decimal(1).scaleb(-places) * 3:.{places}f}"
    return str(int(Decimal(clean)) + 7)


def main(argv=None) -> None:
    total = detected = collisions = 0
    answers = 0
    for path in sorted(RESULTS.glob("chat_*.json")):
        for rec in json.loads(path.read_text())["records"]:
            if not rec.get("passed") or not rec.get("flags", {}).get("grounding_clean") or rec.get("refused"):
                continue
            pool = grounding.evidence_numbers(rec["question"], [json.loads(c) for c in rec["tool_results"]])
            text = rec["answer"]
            nums = [w for w, _ in grounding.extract_numbers(text) if re.fullmatch(r"-?[\d,]+(\.\d+)?", w)]
            used = False
            for w in dict.fromkeys(nums):
                new = mutate(w)
                if grounding.ungrounded_numbers(w, pool):  # already ungrounded alone: skip (cannot happen for clean answers)
                    continue
                if not grounding.ungrounded_numbers(new, pool):
                    collisions += 1
                    continue
                mutated = re.sub(rf"(?<![\w.]){re.escape(w)}(?![\w])", new, text, count=1)
                total += 1
                used = True
                detected += bool(grounding.ungrounded_numbers(mutated, pool))
            answers += used
    out = {"answers_used": answers, "mutations": total, "detected": detected,
           "detection_rate": round(detected / total, 4) if total else None, "collisions_skipped": collisions}
    (RESULTS / "mutation.json").write_text(json.dumps(out, indent=1) + "\n")
    print(out)
