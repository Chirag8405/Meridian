"""Offline tests for the judge experiment's data/label/metric code (no network, no API key)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: F401,E402
import judge_windows as jw  # noqa: E402
from judge_eval import metrics, parse_reply, prompt_for, wilson  # noqa: E402

T0 = datetime(2023, 1, 1, tzinfo=timezone.utc)


def series(prices, start=T0, score=3.0):
    return [{"ts": (start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:00:00Z"), "implied_price": p,
             "volume_usd": 100.0 + i, "trade_count": 5, "is_valid_price": p is not None,
             "anomaly_flag": "NONE", "baseline_status": "RELIABLE", "risk_score": score} for i, p in enumerate(prices)]


def test_sustained_requires_two_consecutive_off_peg_hours():
    rows = series([1.0, 0.97, 1.0, 0.97, 0.96, 1.0])
    hours = jw.sustained_hours(rows)
    assert {jw.parse(rows[3]["ts"]), jw.parse(rows[4]["ts"])} == hours  # the single-hour blip at index 1 is ignored


def test_null_price_counts_as_off_peg():
    rows = series([1.0, None, None, 1.0])
    assert len(jw.sustained_hours(rows)) == 2


def test_window_label_uses_72h_horizon_and_is_independent_of_risk_score(tmp_path):
    prices = [1.0] * 120 + [0.95] * 4 + [1.0] * 20
    rows = series(prices, score=99.0)  # a huge score must not change the label
    p = tmp_path / "s.json"
    import json
    p.write_text(json.dumps({"rows": rows}))
    ws = {w["end_ts"]: w for w in jw.build_event("T", p)}
    onset = T0 + timedelta(hours=120)
    just_inside = (onset - timedelta(hours=72)).strftime("%Y-%m-%dT%H:00:00Z")  # t+72h reaches the depeg
    just_outside = (onset - timedelta(hours=78)).strftime("%Y-%m-%dT%H:00:00Z")
    assert ws[just_inside]["label"] == 1 and ws[just_outside]["label"] == 0
    assert all("risk_score" not in f for w in ws.values() for f in w["features"])


def test_features_are_anonymised():
    w = jw.features(series([1.0, 0.99, 1.01]))
    blob = str(w)
    assert "2023" not in blob and "ts" not in w[0] and w[-1]["hour"] == 0 and w[0]["hour"] == -2
    assert w[1]["price_deviation_pct"] == -1.0


def test_prompt_contains_no_identifying_text():
    win = {"features": jw.features(series([1.0] * 24))}
    text = prompt_for(win).lower()
    import re
    for banned in ("usdc", "ust", "terra", "curve", "2022", "2023", "risk_score", "svb"):
        assert not re.search(rf"\b{banned}\b", text), banned


def test_parse_reply_and_metrics_and_wilson():
    assert parse_reply('noise {"depeg_risk": "high", "confidence": 0.9, "reason": "x"} tail')["depeg_risk"] == "high"
    assert parse_reply('{"depeg_risk": "maybe"}') is None and parse_reply("no json") is None
    m = metrics([(1, 1), (1, 0), (0, 0), (0, 1), (0, 0)])
    assert (m["tp"], m["fn"], m["fp"], m["tn"]) == (1, 1, 1, 2) and m["precision"] == 0.5 and m["false_alarm_rate"] == 0.333
    lo, hi = wilson(1, 2)
    assert 0 < lo < 0.5 < hi < 1 and wilson(0, 0) is None
