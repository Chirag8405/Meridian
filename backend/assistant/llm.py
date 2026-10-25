"""Thin Groq chat-completions client (httpx). Errors are sanitised: no key,
no upstream body, ever reaches a caller."""

import httpx

from assistant.config import GROQ_URL, Settings


class LLMError(Exception):
    """Safe-to-log reason code only (e.g. 'http_429', 'timeout')."""


class GroqClient:
    def __init__(self, settings: Settings):
        self.s = settings

    async def complete(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        if not self.s.api_key:
            raise LLMError("no_api_key")
        body: dict = {
            "model": self.s.model,
            "messages": messages,
            "temperature": 0.1,
            "max_completion_tokens": self.s.max_completion_tokens,
        }
        if tools:
            body["tools"] = tools
        try:
            async with httpx.AsyncClient(timeout=self.s.llm_timeout_seconds) as client:
                resp = await client.post(
                    GROQ_URL, headers={"Authorization": f"Bearer {self.s.api_key}"}, json=body
                )
        except httpx.TimeoutException:
            raise LLMError("timeout") from None
        except httpx.HTTPError:
            raise LLMError("network") from None
        if resp.status_code != 200:
            raise LLMError(f"http_{resp.status_code}")
        try:
            choice = resp.json()["choices"][0]
            return {"message": choice["message"], "finish_reason": choice.get("finish_reason"),
                    "usage": resp.json().get("usage") or {}}
        except (KeyError, IndexError, ValueError):
            raise LLMError("bad_response") from None
