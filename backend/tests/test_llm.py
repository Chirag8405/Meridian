import asyncio

import httpx
import pytest

from assistant.config import Settings
from assistant.llm import GroqClient, LLMError

S = Settings(model="m", api_key="k", proxy_secret="", per_ip_per_min=3, global_per_min=3, daily_cap=3)
OK = {"choices": [{"message": {"role": "assistant", "content": "hi"}, "finish_reason": "stop"}], "usage": {"total_tokens": 5}}


def client(statuses):
    calls = []

    def handler(request):
        calls.append(1)
        code = statuses[min(len(calls) - 1, len(statuses) - 1)]
        return httpx.Response(code, json=OK if code == 200 else {"error": "x"})

    return GroqClient(S, transport=httpx.MockTransport(handler)), calls


def test_400_is_retried_once_then_succeeds():
    c, calls = client([400, 200])
    assert asyncio.run(c.complete([{"role": "user", "content": "q"}]))["message"]["content"] == "hi" and len(calls) == 2


def test_persistent_400_and_other_errors_raise_without_extra_retries():
    c, calls = client([400, 400])
    with pytest.raises(LLMError, match="http_400"):
        asyncio.run(c.complete([]))
    assert len(calls) == 2
    c, calls = client([429])
    with pytest.raises(LLMError, match="http_429"):
        asyncio.run(c.complete([]))
    assert len(calls) == 1
