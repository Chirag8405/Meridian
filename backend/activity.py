"""Pure aggregation logic for the Recent activity graph (and the assistant).

No I/O here: callers pass already-fetched recent_swap_events rows and `now`,
so the same code serves /api/recent-swap-activity, the assistant's
get_recent_activity tool, and the tests.
"""

from datetime import datetime, timedelta, timezone

RECENT_EVENTS_MAX_LIMIT = 100  # matches the recent_swap_events retention policy
RETENTION_HOURS = 48
# window -> (window length, bucket length). Every window yields 12-15 bars.
ACTIVITY_WINDOWS = {
    "15m": (timedelta(minutes=15), timedelta(minutes=1)),
    "1h": (timedelta(hours=1), timedelta(minutes=5)),
    "6h": (timedelta(hours=6), timedelta(minutes=30)),
    "24h": (timedelta(hours=24), timedelta(hours=2)),
}
VALID_SOURCES = {"alchemy_live", "alchemy_getlogs_replay"}


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def matches(row: dict, pair: str | None, pool: str | None, source: str | None) -> bool:
    if pair is not None and (row.get("pair") or "untracked") != pair:
        return False
    if pool is not None and row["pool_name"] != pool:
        return False
    return source is None or row["source"] == source


def compute_activity(
    rows: list, window: str, pair: str | None, pool: str | None, source: str | None, now: datetime
) -> dict:
    """Observed-at bucket counts for one window, zero buckets included."""
    window_len, bucket_len = ACTIVITY_WINDOWS[window]
    bucket_s = int(bucket_len.total_seconds())
    end_epoch = (int(now.timestamp()) // bucket_s + 1) * bucket_s  # end of the current bucket
    window_end = datetime.fromtimestamp(end_epoch, timezone.utc)
    window_start = window_end - window_len

    filter_options = {
        "pairs": sorted({r.get("pair") or "untracked" for r in rows}),
        "pools": sorted({r["pool_name"] for r in rows}),
        "sources": sorted({r["source"] for r in rows}),
    }

    buckets = []
    cursor = window_start
    while cursor < window_end:
        buckets.append({
            "start": cursor, "end": cursor + bucket_len, "total": 0, "live": 0, "gap_filled": 0,
        })
        cursor += bucket_len

    filtered = [r for r in rows if matches(r, pair, pool, source)]
    in_window = []
    for r in filtered:
        observed = parse_ts(r["observed_at"])
        if not (window_start <= observed < window_end):
            continue
        in_window.append(r)
        b = buckets[int((observed - window_start) / bucket_len)]
        b["total"] += 1
        b["live" if r["source"] == "alchemy_live" else "gap_filled"] += 1

    oldest = min((parse_ts(r["observed_at"]) for r in rows), default=None)
    newest = max((parse_ts(r["observed_at"]) for r in filtered), default=None)
    live = sum(1 for r in in_window if r["source"] == "alchemy_live")
    return {
        "window": window,
        "bucket_seconds": bucket_s,
        "window_start": iso(window_start),
        "window_end": iso(window_end),
        "buckets": [
            {**b, "start": iso(b["start"]), "end": iso(b["end"])} for b in buckets
        ],
        "summary": {
            "total": len(in_window),
            "live": live,
            "gap_filled": len(in_window) - live,
            "active_pools": len({r["pool_name"] for r in in_window}),
            "last_observed_at": iso(newest) if newest else None,
        },
        "filter_options": filter_options,
        "retention": {
            "retained_rows": len(rows),
            "retention_hours": RETENTION_HOURS,
            "max_rows": RECENT_EVENTS_MAX_LIMIT,
            "oldest_observed_at": iso(oldest) if oldest else None,
            # True when the selected window reaches back past what is retained.
            "window_exceeds_retention": oldest is not None and oldest > window_start,
        },
    }
