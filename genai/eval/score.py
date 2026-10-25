"""Deterministic scoring of one assistant response against its gold spec."""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from assistant import grounding
from assistant.prompts import REFUSAL_ADVICE, REFUSAL_PREDICTION

UNAVAILABLE = re.compile(
    r"not available|does not (contain|provide|include|have|track|cover|offer)|doesn't (contain|provide|include|have|track|cover|offer)|do not contain|no (live |such |matching )?(data|information|record|reading)|"
    r"not (in|part of|tracked|covered)|cannot|can't|couldn't|unable|no live|isn't (available|tracked)|not something",
    re.I,
)


def norm_text(s: str) -> str:
    s = s.replace("‑", "-").replace("‐", "-").replace("–", "-").replace(" ", " ").replace(" ", " ")
    return s


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9%.]+", "", norm_text(s).lower())


def num_match(written: str, value: Decimal, alt) -> bool:
    """Gold comparison without the grounding allow-list: 0/1/100 must really match."""
    try:
        a = Decimal(str(alt))
    except InvalidOperation:
        return False
    if a == value:
        return True
    places = len(written.replace(",", "").split(".")[1]) if "." in written else 0
    try:
        return a.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP) == value
    except InvalidOperation:
        return False


def check(gold: dict, out: dict, question: str) -> tuple[bool, str]:
    t = gold["type"]
    answer = norm_text(out["answer"])
    if t == "numbers":
        found = grounding.extract_numbers(answer)
        for alts in gold["values"]:
            if not any(num_match(w, v, a) for w, v in found for a in alts):
                return False, f"missing number {alts}"
        return True, ""
    if t == "contains":
        key = norm_key(answer)
        for group in gold["groups"]:
            if not any(norm_key(g) in key for g in group):
                return False, f"missing any of {group}"
        return True, ""
    if t == "forbid":
        key = norm_key(answer)
        for tok in gold["tokens"]:
            if norm_key(tok) in key:
                return False, f"contains forbidden {tok!r}"
        return True, ""
    if t == "refuse":
        want = REFUSAL_ADVICE if gold["kind"] == "advice" else REFUSAL_PREDICTION
        return (out["refused"] and out["answer"] == want), ("" if out["refused"] else "was not refused")
    if t == "unavailable":
        if out["refused"]:
            return False, "refused instead of saying unavailable"
        if not UNAVAILABLE.search(answer):
            return False, "did not say the data is unavailable"
        # Grounded context numbers (e.g. "the data is from 2026") are fine; invented ones are not.
        bad = out["grounding"]["ungrounded_numbers"]
        return (not bad), (f"stated ungrounded numbers {bad}" if bad else "")
    if t == "all":
        for part in gold["parts"]:
            ok, why = check(part, out, question)
            if not ok:
                return False, why
        return True, ""
    raise ValueError(f"unknown gold type {t!r}")


def quality_flags(out: dict) -> dict:
    g = out["grounding"]
    has_numbers = bool(grounding.extract_numbers(out["answer"]))
    return {
        "grounding_clean": not g["ungrounded_numbers"] and not g["invalid_citations"],
        "has_numbers": has_numbers,
        "cited": (not has_numbers) or bool(re.search(r"\[S\d+\]", out["answer"])),
    }
