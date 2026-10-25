from datetime import datetime, timedelta, timezone

from activity import compute_activity

NOW = datetime(2026, 10, 25, 12, 7, 30, tzinfo=timezone.utc)


def row(i, minutes_ago, pool="curve_3pool", src="alchemy_live", pair="USDC_USDT"):
    t = (NOW - timedelta(minutes=minutes_ago)).isoformat()
    return {"event_id": i, "observed_at": t, "pool_name": pool, "source": src, "pair": pair}


ROWS = [row(1, 2), row(2, 7, src="alchemy_getlogs_replay"), row(3, 40, pool="uniswap_v2_usdc_usdt"),
        row(4, 300, pair=None), row(5, 2000)]


def test_bucket_totals_match_summary_and_zero_buckets_kept():
    for w, n in (("15m", 15), ("1h", 12), ("6h", 12), ("24h", 12)):
        r = compute_activity(ROWS, w, None, None, None, NOW)
        assert len(r["buckets"]) == n
        assert sum(b["total"] for b in r["buckets"]) == r["summary"]["total"]
    assert compute_activity(ROWS, "1h", None, None, None, NOW)["summary"]["total"] == 3


def test_filters_and_untracked_pair():
    assert compute_activity(ROWS, "6h", "untracked", None, None, NOW)["summary"]["total"] == 1
    r = compute_activity(ROWS, "1h", None, None, "alchemy_getlogs_replay", NOW)
    assert (r["summary"]["live"], r["summary"]["gap_filled"]) == (0, 1)


def test_buckets_are_utc_aligned_and_flag_retention():
    r = compute_activity(ROWS, "1h", None, None, None, NOW)
    assert r["window_end"] == "2026-10-25T12:10:00Z" and r["window_start"] == "2026-10-25T11:10:00Z"
    assert compute_activity(ROWS, "24h", None, None, None, NOW)["retention"]["window_exceeds_retention"] is False
    assert compute_activity(ROWS[:4], "24h", None, None, None, NOW)["retention"]["window_exceeds_retention"] is True
