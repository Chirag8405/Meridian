"""Freeze the live data the evaluation runs against.

    python genai/eval/run.py snapshot

Reads the public Render API (read-only), writes genai/eval/snapshot/*.json and
_meta.json (export time, frozen "now" for activity questions, content hash).
Re-running changes every live number; gold answers are recomputed from the
snapshot by build_questions, so re-run `questions` afterwards.
"""

import hashlib
import json
from datetime import timedelta

import httpx
from activity import iso, parse_ts
from common import SNAPSHOT, SNAPSHOT_TABLES

RENDER = "https://meridian-czv0.onrender.com"


def main(argv: list[str] | None = None) -> None:
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60) as c:
        data = c.get(f"{RENDER}/api/dashboard-data").raise_for_status().json()
        events = c.get(f"{RENDER}/api/recent-swap-events", params={"limit": 100}).raise_for_status().json()
    h = hashlib.sha256()
    for name in SNAPSHOT_TABLES:
        (SNAPSHOT / f"{name}.json").write_text(json.dumps(data[name], separators=(",", ":")))
        h.update(json.dumps(data[name], sort_keys=True).encode())
    (SNAPSHOT / "recent_swap_events.json").write_text(json.dumps(events, separators=(",", ":")))
    h.update(json.dumps(events, sort_keys=True).encode())
    (SNAPSHOT / "metadata.json").write_text(json.dumps([data["metadata"]]))
    # Frozen "now" for activity questions: just after the newest observed event.
    newest = max(parse_ts(e["observed_at"]) for e in events)
    meta = {
        "exported_at": data["metadata"]["exported_at"],
        "now": iso(newest + timedelta(seconds=30)),
        "events": len(events),
        "sha256": h.hexdigest(),
    }
    (SNAPSHOT / "_meta.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"snapshot written: {meta}")
