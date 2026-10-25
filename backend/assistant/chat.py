"""Orchestration: tool-calling loop -> answer -> numeric grounding check."""

import json
import re
from datetime import datetime, timezone
from typing import Protocol

from assistant import grounding
from assistant.config import Settings
from assistant.data import DataSource
from assistant.prompts import NO_MORE_TOOLS, SYSTEM_PROMPT, refusal_for
from assistant.retrieval import Bm25Index
from assistant.tools import TOOL_SCHEMAS, run_tool, search_docs_sync

FALLBACK = "I couldn't produce an answer from the available data."


class DataUnavailable(Exception):
    """Every tool call failed upstream; answering "the data does not contain it" would be a lie."""


class LLM(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict: ...


def _sources_from_result(name: str, result: dict, sources: list[dict], now: str) -> None:
    """Assign S-ids in place: one per data result, one per retrieved doc chunk."""
    if name == "search_docs" and "chunks" in result:
        for chunk in result["chunks"]:
            sid = f"S{len(sources) + 1}"
            chunk["source_id"] = sid
            sources.append({"id": sid, "kind": "doc", "label": f'{chunk["file"]} > {chunk["heading"]}'})
    else:
        sid = f"S{len(sources) + 1}"
        result["source_id"] = sid
        sources.append({"id": sid, "kind": "data", "label": result.get("label", name), "tool": name,
                        "fetched_at": now})


_EXPLAIN = re.compile(r"\b(why|how (does|do|did|is|was|are|were)|explain|what does .* mean|what is|meaning|method|methodology)\b", re.I)


def _prefetch_docs(question: str, index: Bm25Index, messages: list[dict], results: list[dict],
                   sources: list[dict], now: str) -> bool:
    """For why/how/explain questions, always put the relevant doc excerpts in front of the
    model (a synthetic search_docs call). Prompt rule 8 alone was not followed reliably."""
    if not _EXPLAIN.search(question):
        return False
    result = search_docs_sync(index, question)
    if not result["chunks"]:
        return False
    args = json.dumps({"query": question})
    _sources_from_result("search_docs", result, sources, now)
    results.append(result)
    messages.append({"role": "assistant", "content": "", "tool_calls": [
        {"id": "prefetch_docs", "type": "function", "function": {"name": "search_docs", "arguments": args}}]})
    messages.append({"role": "tool", "tool_call_id": "prefetch_docs", "name": "search_docs",
                     "content": json.dumps(result, default=str)})
    return True


def _check(answer: str, question: str, results: list[dict], sources: list[dict]) -> tuple[list[str], list[str]]:
    pool = grounding.evidence_numbers(question, results)
    return (grounding.ungrounded_numbers(answer, pool),
            grounding.invalid_citations(answer, {s["id"] for s in sources}))


async def answer_question(
    question: str, history: list[dict], src: DataSource, index: Bm25Index, llm: LLM, settings: Settings
) -> dict:
    refusal = refusal_for(question)
    if refusal:
        return {"answer": refusal, "sources": [], "refused": True,
                "grounding": {"checked": False, "ungrounded_numbers": [], "invalid_citations": [], "retried": False},
                "tool_calls": 0}

    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": h["role"], "content": h["content"][: settings.max_question_chars]}
                 for h in history[-4:] if h.get("role") in ("user", "assistant")]
    messages.append({"role": "user", "content": question})

    sources: list[dict] = []
    results: list[dict] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    calls = 1 if _prefetch_docs(question, index, messages, results, sources, now) else 0
    rounds = 0
    empty_retries = 0
    data_failures = 0
    final = ""
    for _ in range(settings.max_tool_rounds + 3):
        allow_tools = rounds < settings.max_tool_rounds
        if not allow_tools and messages[-1].get("role") != "system":
            messages.append({"role": "system", "content": NO_MORE_TOOLS})
        out = await llm.complete(messages, TOOL_SCHEMAS if allow_tools else None)
        msg = out["message"]
        tool_calls = msg.get("tool_calls") if allow_tools else None
        if not tool_calls:
            final = (msg.get("content") or "").strip() if out.get("finish_reason") != "length" else ""
            if not final and empty_retries < 1:  # the model occasionally returns nothing; ask once more
                empty_retries += 1
                continue
            break
        rounds += 1
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls})
        for n, tc in enumerate(tool_calls):
            name = tc["function"]["name"]
            calls += 1
            if n >= settings.max_calls_per_round:
                result = {"error": "tool call limit reached"}
            else:
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                    if not isinstance(args, dict):
                        raise ValueError
                except ValueError:
                    result = {"error": "arguments were not valid JSON"}
                else:
                    result = await run_tool(name, args, src, index)
                    data_failures += result.get("error") == "data unavailable"
                    if "error" not in result:
                        _sources_from_result(name, result, sources, now)
                        results.append(result)
            messages.append({"role": "tool", "tool_call_id": tc["id"], "name": name,
                             "content": json.dumps(result, default=str)})

    if data_failures and not results:
        raise DataUnavailable

    retried = False
    bad_nums, bad_cites = _check(final, question, results, sources) if final else ([], [])
    if final and (bad_nums or bad_cites):
        retried = True
        problems = []
        if bad_nums:
            problems.append(f"these numbers are not in the evidence: {', '.join(bad_nums)}")
        if bad_cites:
            problems.append(f"these citations do not exist: {', '.join(bad_cites)}")
        messages.append({"role": "assistant", "content": final})
        messages.append({"role": "user", "content": (
            "Rewrite your answer: " + "; ".join(problems) + ". Use only numbers and [S#] citations from "
            "the evidence, or say the value is not available.")})
        out = await llm.complete(messages, None)
        if out.get("finish_reason") != "length":
            final = (out["message"].get("content") or "").strip() or final
        bad_nums, bad_cites = _check(final, question, results, sources)

    used = set(re.findall(r"\[(S\d+)\]", final))
    return {
        "answer": final or FALLBACK,
        "sources": [s for s in sources if s["id"] in used] if used else sources,
        "refused": False,
        "grounding": {"checked": bool(final), "ungrounded_numbers": bad_nums,
                      "invalid_citations": bad_cites, "retried": retried},
        "tool_calls": calls,
    }
