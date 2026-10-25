"""Shared pieces for the offline GenAI evaluation (docs/GENAI_ASSISTANT_PLAN.md, Part B/C).

Run everything from the repo root, e.g. `python genai/eval/run.py chat --split dev`.
Uses the backend/assistant package exactly as Render runs it.
"""

import asyncio
import json
import os
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = Path(__file__).resolve().parent
SNAPSHOT = EVAL / "snapshot"
RESULTS = EVAL / "results"
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(EVAL))

SNAPSHOT_TABLES = [
    "current_risk", "current_risk_live", "usdc_crisis_timeline", "ust_crisis_timeline",
    "live_price_timeline", "evaluation_summary", "classifier_metrics", "wallet_rankings",
]


def load_env() -> dict:
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def snapshot_now() -> datetime:
    meta = json.loads((SNAPSHOT / "_meta.json").read_text())
    return datetime.fromisoformat(meta["now"].replace("Z", "+00:00")).astimezone(timezone.utc)


class SnapshotSource:
    """DataSource over the frozen snapshot, so every run sees identical data."""

    def __init__(self):
        self._cache: dict[str, list] = {}

    async def table(self, name: str, order: str | None = None) -> list[dict]:
        if name not in self._cache:
            path = SNAPSHOT / f"{name}.json"
            self._cache[name] = json.loads(path.read_text()) if path.exists() else []
        return self._cache[name]

    def rows(self, name: str) -> list[dict]:
        return asyncio.run(self.table(name))


class PacedLLM:
    """Wraps a real client: keeps under Groq's tokens/minute, retries 429s, and
    records per-question token use and the last message list it was sent."""

    def __init__(self, inner, tpm_budget: int = 6500, est_call_tokens: int = 2500):
        from assistant.llm import LLMError

        self._LLMError = LLMError
        self.inner, self.budget, self.est = inner, tpm_budget, est_call_tokens
        self._window: deque = deque()  # (time, tokens)
        self.calls = 0
        self.tokens = 0
        self.last_messages: list[dict] = []

    def reset(self) -> None:
        self.calls = self.tokens = 0
        self.last_messages = []

    async def _throttle(self) -> None:
        while True:
            now = time.time()
            while self._window and now - self._window[0][0] >= 60:
                self._window.popleft()
            if sum(t for _, t in self._window) + self.est <= self.budget or not self._window:
                return
            await asyncio.sleep(max(1.0, 61 - (now - self._window[0][0])))

    async def complete(self, messages, tools=None):
        self.last_messages = messages
        for attempt in range(5):
            await self._throttle()
            try:
                out = await self.inner.complete(messages, tools)
                break
            except self._LLMError as exc:
                if str(exc) == "http_429" and attempt < 4:
                    await asyncio.sleep(20 * (attempt + 1))
                    continue
                raise
        used = (out.get("usage") or {}).get("total_tokens", self.est)
        self._window.append((time.time(), used))
        self.calls += 1
        self.tokens += used
        return out
