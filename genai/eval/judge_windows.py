"""Part C, step 1: build anonymised 24h windows + labels + the non-LLM predictors.

    python genai/eval/run.py judge-windows

Input : genai/eval/judge/series_usdc.json, series_ust.json (spark/export_judge_series.scala)
Output: genai/eval/judge/windows.json

DESIGN, fixed before any result was looked at (plan section 7):
  * Unit: a window ending at hour t, showing the previous 24 hourly rows.
  * Label y(t) = 1 iff a SUSTAINED price depeg is ongoing or begins within the next 72 hours,
    i.e. some hour h in [t, t+72h] belongs to a run of >= 2 consecutive hours where the price
    is invalid/null or |price - 1| >= 1% (the same definition as spark/evaluation_summary.scala
    and docs/FINDINGS.md). The label never uses risk_score.
    The 72h horizon is the measured USDC lead time the project claims, so this asks the
    judge to do the job the early-warning claim is about.
  * Predictors, all evaluated on the same windows:
      rule      : risk_score(t) >= 7.18 and risk_score(t-1h) >= 7.18  (the project's elevated threshold,
                  sustained 2h, as in evaluation_summary; 7.18 comes from USDC calm data and is applied
                  to UST as a cross-pair threshold, exactly as there)
      price_1pct: |p-1| >= 1% at t and t-1h   (a plain "depeg alarm": by construction it fires only once
                  a depeg is already underway)
      price_05pct: same at 0.5%
      majority  : always the more common label of that event's windows
  * What the LLM sees (judge_run.py): hours labelled -23..0, price deviation from $1 in percent, volume and
    trade count as ratios to the window's own median, anomaly flag, price-valid flag. No dates, pair or
    event names, absolute prices/volumes, scores or cluster ids.
  * LLM subset: per event up to 30 positive + 30 negative windows, seed 11. Deterministic predictors are
    reported on ALL windows and on this subset.
"""

import json
import random
import statistics
from datetime import datetime, timedelta

from common import EVAL

JUDGE = EVAL / "judge"
THRESHOLD = 7.18
HORIZON_H = 72
WINDOW_H = 24
STRIDE_H = 6
SEED = 11
PER_CLASS = 30


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def off_peg(row: dict, tol: float) -> bool:
    p = row["implied_price"]
    return p is None or abs(p - 1.0) >= tol


def sustained_hours(rows: list[dict], tol: float = 0.01) -> set[datetime]:
    """Hours belonging to a run of >= 2 consecutive (hourly-adjacent) off-peg rows."""
    out, run = set(), []
    for r in rows:
        t = parse(r["ts"])
        if off_peg(r, tol) and (not run or t - run[-1][0] == timedelta(hours=1)):
            run.append((t, r))
        else:
            if len(run) >= 2:
                out |= {x[0] for x in run}
            run = [(t, r)] if off_peg(r, tol) else []
    if len(run) >= 2:
        out |= {x[0] for x in run}
    return out


def features(window: list[dict]) -> list[dict]:
    vols = [r["volume_usd"] for r in window if r["volume_usd"] is not None]
    trades = [r["trade_count"] for r in window if r["trade_count"] is not None]
    mv = statistics.median(vols) if vols else None
    mt = statistics.median(trades) if trades else None
    out = []
    n = len(window)
    for i, r in enumerate(window):
        p = r["implied_price"]
        out.append({
            "hour": i - (n - 1),
            "price_deviation_pct": None if p is None else round((p - 1.0) * 100, 4),
            "volume_vs_window_median": None if not mv or r["volume_usd"] is None else round(r["volume_usd"] / mv, 3),
            "trades_vs_window_median": None if not mt or r["trade_count"] is None else round(r["trade_count"] / mt, 3),
            "anomaly_flag": r["anomaly_flag"],
            "price_valid": bool(r["is_valid_price"]) if r["is_valid_price"] is not None else None,
        })
    return out


def build_event(label: str, path) -> list[dict]:
    rows = json.loads(path.read_text())["rows"]
    by_ts = {parse(r["ts"]): r for r in rows}
    sus = sustained_hours(rows)
    windows = []
    for r in rows:
        t = parse(r["ts"])
        if t.hour % STRIDE_H:
            continue
        hist = [by_ts[t - timedelta(hours=k)] for k in range(WINDOW_H - 1, -1, -1) if (t - timedelta(hours=k)) in by_ts]
        if len(hist) < 20:  # need nearly full history; gaps are not imputed
            continue
        y = int(any((t + timedelta(hours=k)) in sus for k in range(0, HORIZON_H + 1)))
        prev = by_ts.get(t - timedelta(hours=1))

        def sustained_flag(tol):
            return bool(prev is not None and off_peg(r, tol) and off_peg(prev, tol))

        windows.append({
            "id": f"{label}-{t:%Y%m%dT%H}", "event": label, "end_ts": r["ts"], "label": y,
            "rule_score": r["risk_score"],
            "rule": bool(prev is not None and r["risk_score"] >= THRESHOLD and prev["risk_score"] >= THRESHOLD),
            "price_1pct": sustained_flag(0.01), "price_05pct": sustained_flag(0.005),
            "baseline_status": r["baseline_status"], "hours_present": len(hist),
            "features": features(hist),
        })
    maj = int(sum(w["label"] for w in windows) * 2 >= len(windows)) if windows else 0
    for w in windows:
        w["majority"] = bool(maj)
    return windows


def select_subset(windows: list[dict]) -> set[str]:
    rng = random.Random(SEED)
    chosen = set()
    for event in sorted({w["event"] for w in windows}):
        for y in (1, 0):
            pool = sorted((w["id"] for w in windows if w["event"] == event and w["label"] == y))
            chosen |= set(rng.sample(pool, min(PER_CLASS, len(pool))))
    return chosen


def main(argv=None) -> None:
    windows = build_event("USDC", JUDGE / "series_usdc.json") + build_event("UST", JUDGE / "series_ust.json")
    subset = select_subset(windows)
    for w in windows:
        w["llm_subset"] = w["id"] in subset
    meta = {
        "threshold": THRESHOLD, "horizon_h": HORIZON_H, "window_h": WINDOW_H, "stride_h": STRIDE_H,
        "seed": SEED, "per_class": PER_CLASS,
        "counts": {e: {"windows": sum(w["event"] == e for w in windows),
                       "positive": sum(w["event"] == e and w["label"] == 1 for w in windows),
                       "llm_subset": sum(w["event"] == e and w["llm_subset"] for w in windows)}
                   for e in ("USDC", "UST")},
    }
    (JUDGE / "windows.json").write_text(json.dumps({"meta": meta, "windows": windows}, separators=(",", ":")))
    print(json.dumps(meta, indent=1))
