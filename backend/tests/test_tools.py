import asyncio

from assistant.retrieval import Bm25Index
from assistant.tools import run_tool

from helpers import EVAL_ROWS, LIVE_ROWS, FakeSource

INDEX = Bm25Index([{"id": "F#1", "file": "FINDINGS.md", "heading_path": "Lead time", "text": "Lead time was 72 hours."}])


def run(name, args, tables=None):
    src = FakeSource(tables or {"current_risk_live": LIVE_ROWS, "evaluation_summary": EVAL_ROWS})
    return asyncio.run(run_tool(name, args, src, INDEX))


def test_live_risk_rounds_filters_and_drops_advisory():
    r = run("get_live_risk", {"pair": "USDC_DAI", "project": "curve"})
    assert r["row_count"] == 1
    row = r["rows"][0]
    assert row["risk_score"] == 4.3575 and row["window_start_ts"] == "2026-10-25T03:00:00Z"
    assert "advisory" not in row


def test_event_evaluation_hides_nulls_and_volume():
    rows = run("get_event_evaluation", {"event_label": "USDC_MAR2023"})["rows"]
    assert rows[0]["lead_time_hours"] == 72.0 and "calm_caveat" not in rows[0]
    assert "calm_avg_volume_usd" not in rows[0]


def test_unknown_tool_and_bad_args_return_errors_not_exceptions():
    assert "error" in run("drop_table", {})
    assert "error" in run("get_live_risk", {"nonsense": 1})


def test_event_timeline_summary():
    tl = [{"window_start_ts": f"2023-03-1{d}T00:00:00+00:00", "implied_price": p, "volume_usd": 1.0}
          for d, p in ((0, 1.0), (1, 0.97), (2, 0.88))]
    r = run("get_event_timeline", {"event": "USDC_MAR2023"}, {"usdc_crisis_timeline": tl})
    assert r["min_price"] == 0.88 and r["first_hour_at_least_1pct_off_peg"] == "2023-03-11T00:00:00Z"
    assert "error" in run("get_event_timeline", {"event": "FOO"}, {})


def test_search_docs():
    r = run("search_docs", {"query": "lead time"})
    assert r["chunks"][0]["id"] == "F#1"


def test_oversized_result_is_replaced():
    big = [{"pair": "P", "project": "x", "risk_score": 1.0, "window_start_ts": "2026-01-01T00:00:00Z",
            "source": "s" * 200} for _ in range(100)]
    assert "error" in run("get_live_risk", {}, {"current_risk_live": big})


def test_garbage_model_arguments_are_argument_errors_not_data_failures():
    r = run("get_live_prices", {"pair": "USDC_DAI", "hours": "abc"}, {"live_price_timeline": []})
    assert r["error"].startswith("bad arguments")
