"""Best-effort Groq explanations for the latest live risk rows.

This runs once per dashboard publish, after Spark has produced the latest
live scores and before the JSON is pushed to Supabase. A model failure never
blocks publishing the score itself.
"""

import json
import os
import sys
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
RISK_FILE = PROJECT_ROOT / "dashboard" / "data" / "current_risk_live.json"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"
GROUNDING_FIELDS = ("price_dev", "cluster_id", "cluster_severity", "wallet_concentration_severity")


def load_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    values = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def prompt_for(row: dict) -> str:
    wallet = row.get("wallet_concentration_severity")
    wallet_text = "not available" if wallet is None else f"{wallet:.4f}"
    return (
        "Write exactly 2 or 3 short sentences in plain English explaining the current "
        "risk state for this stablecoin pair. Use only the supplied numbers. Do not "
        "claim a cause, trend, prediction, or event that the numbers do not establish. "
        "Mention uncertainty when a value is unavailable. Do not use headings or bullets.\n\n"
        f"Pair: {row.get('pair')} on {row.get('project')}\n"
        f"Risk score (0-100): {row.get('risk_score')}\n"
        f"Price deviation feature: {row.get('price_dev')}\n"
        f"Cluster assignment: {row.get('cluster_id')}\n"
        f"Cluster severity (0-1): {row.get('cluster_severity')}\n"
        f"Wallet concentration severity (0-1): {wallet_text}"
    )


def generate(row: dict, api_key: str) -> str | None:
    response = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": MODEL,
            "temperature": 0.2,
            "max_completion_tokens": 512,
            "messages": [
                {"role": "system", "content": "You are a careful risk analyst. Follow the numeric grounding rules exactly."},
                {"role": "user", "content": prompt_for(row)},
            ],
        },
        timeout=30,
    )
    response.raise_for_status()
    content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    content = " ".join(content.split())
    return content or None


def main() -> None:
    if not RISK_FILE.exists():
        sys.exit(f"Missing {RISK_FILE} — run the Spark export first")

    rows = json.loads(RISK_FILE.read_text())
    api_key = load_env().get("GROQ_API_KEY", "")
    if not api_key:
        for row in rows:
            row["advisory"] = None
        RISK_FILE.write_text(json.dumps(rows, separators=(",", ":")))
        print("GROQ_API_KEY not set; publishing scores without advisories.")
        return

    generated = 0
    for row in rows:
        row["advisory"] = None
        if any(row.get(field) is None for field in GROUNDING_FIELDS):
            print(
                f"Advisory skipped for {row.get('pair')} / {row.get('project')}: "
                "computed grounding fields are incomplete.",
                file=sys.stderr,
            )
            continue
        try:
            row["advisory"] = generate(row, api_key)
            generated += row["advisory"] is not None
        except requests.RequestException as exc:
            print(f"Advisory failed for {row.get('pair')} / {row.get('project')}: {exc}", file=sys.stderr)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            print(f"Invalid advisory response for {row.get('pair')} / {row.get('project')}: {exc}", file=sys.stderr)

    RISK_FILE.write_text(json.dumps(rows, separators=(",", ":")))
    print(f"Generated {generated}/{len(rows)} risk advisories using {MODEL}.")


if __name__ == "__main__":
    main()
