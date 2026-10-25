"""Read-only tools the model may call. No SQL, no writes; every tool returns a
compact dict (floats rounded to 4 dp, timestamps in UTC) with a `row_count`
so counts the answer states are themselves evidence."""

import json
from datetime import datetime, timezone
from typing import Any

from activity import ACTIVITY_WINDOWS, VALID_SOURCES, compute_activity, parse_ts
from assistant.data import DataSource
from assistant.retrieval import Bm25Index

EVENTS = ("USDC_MAR2023", "UST_MAY2022")
WALLET_WINDOWS = ("USDC_MAR2023_CRISIS", "UST_MAY2022_CRISIS")
# Overridden by the offline evaluation so activity questions are reproducible
# against a frozen snapshot (genai/eval).
now = lambda: datetime.now(timezone.utc)  # noqa: E731

MAX_RESULT_CHARS = 7500  # keeps each tool result well inside the 8K tokens/min budget


def _utc(value: Any) -> Any:
    if isinstance(value, str) and len(value) >= 19 and value[4] == "-" and value[10] in "T ":
        try:
            return parse_ts(value).strftime("%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return value
    return value


def clean(x: Any) -> Any:
    """Round floats to 4 dp, normalise timestamps to UTC, drop nulls."""
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items() if v is not None}
    if isinstance(x, list):
        return [clean(v) for v in x]
    return _utc(x)


def _pick(rows: list[dict], cols: tuple[str, ...]) -> list[dict]:
    return [clean({c: r.get(c) for c in cols}) for r in rows]


def _filter(rows: list[dict], **eq) -> list[dict]:
    return [r for r in rows if all(v is None or r.get(k) == v for k, v in eq.items())]


async def get_live_risk(src: DataSource, pair: str | None = None, project: str | None = None) -> dict:
    rows = _filter(await src.table("current_risk_live", order="pair,project"), pair=pair, project=project)
    cols = ("pair", "project", "risk_score", "window_start_ts", "source", "price_dev",
            "cluster_id", "cluster_severity", "wallet_concentration_severity")
    return {"label": "current_risk_live (latest live reading per pair/DEX)",
            "row_count": len(rows), "rows": _pick(rows, cols)}


async def get_historical_risk(src: DataSource, pair: str | None = None, project: str | None = None) -> dict:
    rows = _filter(await src.table("current_risk", order="pair,project"), pair=pair, project=project)
    cols = ("pair", "project", "baseline_status", "risk_score", "window_start_ts")
    return {"label": "current_risk (latest scored window per pair/DEX; may be old for quiet pairs)",
            "row_count": len(rows), "rows": _pick(rows, cols)}


async def get_event_evaluation(src: DataSource, event_label: str | None = None) -> dict:
    rows = _filter(await src.table("evaluation_summary", order="event_label"), event_label=event_label)
    drop = {"calm_avg_volume_usd", "crisis_avg_volume_usd"}
    rows = [{k: v for k, v in r.items() if k not in drop} for r in rows]
    return {"label": "evaluation_summary (early-warning lead time and false alarms per real event)",
            "row_count": len(rows), "rows": clean(rows)}


async def get_event_timeline(src: DataSource, event: str) -> dict:
    table = {"USDC_MAR2023": "usdc_crisis_timeline", "UST_MAY2022": "ust_crisis_timeline"}.get(event)
    if table is None:
        return {"error": f"event must be one of {list(EVENTS)}"}
    rows = [r for r in await src.table(table, order="window_start_ts") if r.get("implied_price") is not None]
    if not rows:
        return {"label": table, "row_count": 0}
    low = min(rows, key=lambda r: r["implied_price"])
    high = max(rows, key=lambda r: r["implied_price"])
    off_peg = next((r for r in rows if abs(r["implied_price"] - 1) >= 0.01), None)
    return clean({
        "label": f"{table} (hourly implied price inside the labeled crisis window)",
        "row_count": len(rows),
        "first_hour": rows[0]["window_start_ts"], "last_hour": rows[-1]["window_start_ts"],
        "min_price": low["implied_price"], "min_price_hour": low["window_start_ts"],
        "max_price": high["implied_price"], "max_price_hour": high["window_start_ts"],
        "first_hour_at_least_1pct_off_peg": off_peg["window_start_ts"] if off_peg else None,
        "note": "descriptive summary of the labeled window only; sustained-depeg onset is in evaluation_summary",
    })


async def get_live_prices(src: DataSource, pair: str, project: str | None = None, hours: int = 24) -> dict:
    hours = max(1, min(int(hours), 168))
    rows = [r for r in await src.table("live_price_timeline", order="pair,project,window_start_ts")
            if r["pair"] == pair and (project is None or r["project"] == project)
            and r.get("implied_price") is not None]
    if not rows:
        return {"label": "live_price_timeline", "row_count": 0}
    out = []
    for proj in sorted({r["project"] for r in rows}):
        pr = sorted((r for r in rows if r["project"] == proj), key=lambda r: parse_ts(r["window_start_ts"]))
        latest = parse_ts(pr[-1]["window_start_ts"])
        recent = [r for r in pr if (latest - parse_ts(r["window_start_ts"])).total_seconds() < hours * 3600]
        prices = [r["implied_price"] for r in recent]
        out.append({
            "project": proj, "latest_hour": pr[-1]["window_start_ts"],
            "latest_price": pr[-1]["implied_price"], "hourly_windows_in_range": len(recent),
            "min_price": min(prices), "max_price": max(prices),
            "mean_price": sum(prices) / len(prices),
        })
    return clean({"label": f"live_price_timeline ({pair}; hourly windows ending at the latest available hour, last {hours}h)",
                  "row_count": len(out), "rows": out})


async def get_recent_activity(src: DataSource, window: str = "1h", pair: str | None = None,
                              pool: str | None = None, source: str | None = None) -> dict:
    if window not in ACTIVITY_WINDOWS:
        return {"error": f"window must be one of {list(ACTIVITY_WINDOWS)}"}
    if source is not None and source not in VALID_SOURCES:
        return {"error": f"source must be one of {sorted(VALID_SOURCES)}"}
    rows = await src.table("recent_swap_events", order="observed_at.desc,event_id.desc")
    res = compute_activity(rows, window, pair, pool, source, now())
    busiest = max(res["buckets"], key=lambda b: b["total"])
    return clean({
        "label": f"recent_swap_events (swaps the live feed observed in the last {window}; counts are descriptive, not risk)",
        "row_count": res["summary"]["total"],
        "summary": res["summary"], "bucket_minutes": res["bucket_seconds"] // 60,
        "busiest_bucket": busiest if busiest["total"] else None,
        "retention": res["retention"],
    })


async def get_classifier_metrics(src: DataSource) -> dict:
    rows = await src.table("classifier_metrics", order="direction,scorer")
    return {"label": "classifier_metrics (ML crisis classifier vs rule-based baseline)",
            "row_count": len(rows), "rows": clean(rows)}


async def get_wallet_rankings(src: DataSource, window_label: str | None = None, top_n: int = 5) -> dict:
    top_n = max(1, min(int(top_n), 10))
    rows = [r for r in await src.table("wallet_rankings", order="window_label,rank_within_window")
            if window_label is None or r["window_label"] == window_label]
    rows = [r for r in rows if r["rank_within_window"] <= top_n]
    return {"label": "wallet_rankings (PageRank influence per crisis window)",
            "row_count": len(rows), "rows": clean(rows)}


def search_docs_sync(index: Bm25Index, query: str, k: int = 3) -> dict:
    hits = index.search(query, k=k)
    return {"label": "project documentation excerpts", "row_count": len(hits),
            "chunks": [{"id": h["id"], "file": h["file"], "heading": h["heading_path"], "text": h["text"]}
                       for h in hits]}


def _fn(name: str, description: str, props: dict, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required or []}}}


_PAIR = {"type": "string", "description": "e.g. USDC_DAI or USDC_USDT"}
_PROJECT = {"type": "string", "description": "DEX: curve or uniswap_v2"}

TOOL_SCHEMAS = [
    _fn("get_live_risk", "Latest live risk score (0-100) per pair and DEX, with its inputs. Omit all arguments to get every pair and DEX (4 rows).", {"pair": _PAIR, "project": _PROJECT}),
    _fn("get_historical_risk", "Latest scored window per pair/DEX across all 7 tracked pairs, including UST. Omit arguments for all rows.", {"pair": _PAIR, "project": _PROJECT}),
    _fn("get_event_evaluation", "Measured early-warning results (lead time, false alarms, peak score) for the two real events.",
        {"event_label": {"type": "string", "enum": list(EVENTS)}}),
    _fn("get_event_timeline", "Summary of the hourly price inside one real crisis window (lowest price, when it left the peg).",
        {"event": {"type": "string", "enum": list(EVENTS)}}, ["event"]),
    _fn("get_live_prices", "Summary of live hourly implied prices for a USDC pair (latest, min, max, mean).",
        {"pair": _PAIR, "project": _PROJECT, "hours": {"type": "integer", "description": "lookback hours, 1-168"}}, ["pair"]),
    _fn("get_recent_activity", "How many swaps the live feed observed in a recent window.",
        {"window": {"type": "string", "enum": list(ACTIVITY_WINDOWS)}, "pair": {"type": "string", "description": "USDC_DAI, USDC_USDT or untracked"},
         "pool": {"type": "string", "description": "pool name, e.g. curve_3pool"},
         "source": {"type": "string", "enum": sorted(VALID_SOURCES)}}),
    _fn("get_classifier_metrics", "Precision/recall/F1/PR-AUC of the ML crisis classifier versus the rule-based score.", {}),
    _fn("get_wallet_rankings", "Most influential wallets (PageRank) in each crisis window.",
        {"window_label": {"type": "string", "enum": list(WALLET_WINDOWS)}, "top_n": {"type": "integer"}}),
    _fn("search_docs", "Search project documentation (findings, architecture, scope) for explanations and methodology.",
        {"query": {"type": "string"}}, ["query"]),
]


async def run_tool(name: str, args: dict, src: DataSource, index: Bm25Index) -> dict:
    """Execute one tool; never raises (errors are returned as data)."""
    try:
        if name == "search_docs":
            result = search_docs_sync(index, str(args.get("query", ""))[:200])
        else:
            fn = {
                "get_live_risk": get_live_risk, "get_historical_risk": get_historical_risk,
                "get_event_evaluation": get_event_evaluation, "get_event_timeline": get_event_timeline,
                "get_live_prices": get_live_prices, "get_recent_activity": get_recent_activity,
                "get_classifier_metrics": get_classifier_metrics, "get_wallet_rankings": get_wallet_rankings,
            }.get(name)
            if fn is None:
                return {"error": f"unknown tool {name!r}"}
            result = await fn(src, **args)
    except (TypeError, ValueError) as exc:
        return {"error": f"bad arguments: {exc}"}
    except Exception:  # upstream/data failure; no details leak to the model or user
        return {"error": "data unavailable"}
    text = json.dumps(result, default=str)
    if len(text) > MAX_RESULT_CHARS:
        result = {"label": result.get("label"), "error": "result too large; narrow the request"}
    return result
