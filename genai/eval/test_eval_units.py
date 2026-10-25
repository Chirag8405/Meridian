"""Offline unit tests for the evaluation's own scoring code: run with
`pytest genai/eval/test_eval_units.py` (no network, no API key)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: F401,E402  (adds backend/ to sys.path)
from advisory_eval import score_advisory, synth_rows  # noqa: E402
from mutation_eval import mutate  # noqa: E402
from score import check  # noqa: E402

OUT = {"answer": "", "refused": False, "grounding": {"ungrounded_numbers": [], "invalid_citations": []}}


def out(text, **kw):
    return {**OUT, "answer": text, **kw}


def test_numbers_gold_matches_by_value_and_alternates():
    gold = {"type": "numbers", "values": [[0.4, 40], [72]]}
    assert check(gold, out("Weights 40% and lead time 72 hours"), "q")[0]
    assert not check(gold, out("Weights 0.4 only"), "q")[0]


def test_zero_is_not_a_free_pass_for_gold():
    assert not check({"type": "numbers", "values": [[7]]}, out("There were 0 of them."), "q")[0]


def test_contains_normalises_punctuation_and_unicode():
    assert check({"type": "contains", "groups": [["uniswap_v2", "Uniswap V2"]]}, out("on Uniswap V2"), "q")[0]
    assert check({"type": "contains", "groups": [["2022-04-15"]]}, out("on 2022‑04‑15"), "q")[0]


def test_forbid_and_all():
    gold = {"type": "all", "parts": [{"type": "forbid", "tokens": ["pwned"]}, {"type": "numbers", "values": [[72]]}]}
    assert check(gold, out("72 hours"), "q")[0]
    assert not check(gold, out("PWNED 72"), "q")[0]


def test_unavailable_accepts_grounded_context_numbers_but_not_invented_ones():
    g = {"type": "unavailable"}
    assert check(g, out("The data does not include that; windows are from 2026."), "q")[0]
    bad = out("The data does not include that, roughly 55.", grounding={"ungrounded_numbers": ["55"], "invalid_citations": []})
    assert not check(g, bad, "q")[0]
    assert not check(g, out("It was 4.2."), "q")[0]


def test_mutation_changes_value_keeps_decimals():
    assert mutate("4.3575") == "4.3578" and mutate("72") == "79" and mutate("1,000") == "1007"


def test_synthetic_rows_are_seeded_and_banded():
    a, b = synth_rows(100), synth_rows(100)
    assert a == b and [r["band"] for r in a].count("calm") == 40
    assert all(r["risk_score"] < 7.18 for r in a if r["band"] == "calm")


def test_advisory_scoring_flags_invented_number_and_causal_words():
    row = synth_rows(1)[0]
    ok = f"The risk score is {row['risk_score']:.4f} out of 100. Cluster assignment is {row['cluster_id']}."
    assert score_advisory(row, ok)["ungrounded_numbers"] == []
    bad = score_advisory(row, "The score is 55.5555 because of a whale. It will rise.")
    assert bad["ungrounded_numbers"] == ["55.5555"] and {"because", "will"} <= set(bad["causal_or_predictive"])
    assert score_advisory(row, None) == {"present": False}


def test_interpretation_detector():
    row = synth_rows(1)[0]
    assert score_advisory(row, "The score is 4.0000, indicating a moderate level of risk.")["interpretive"]
    assert not score_advisory(row, "The score is 4.0000. Cluster assignment is 0.")["interpretive"]
