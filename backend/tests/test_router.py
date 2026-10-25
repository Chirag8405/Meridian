import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from assistant.config import Settings
from assistant.retrieval import Bm25Index
from assistant.router import create_router

from helpers import LIVE_ROWS, FakeLLM, FakeSource, tool_call

TABLES = {"current_risk_live": LIVE_ROWS, "metadata": [{"exported_at": "t1"}],
          "recent_swap_events": [{"observed_at": "2026-10-25T00:00:00Z", "event_id": 1}]}


def client(script, **kw):
    s = Settings(model="m", api_key="k", proxy_secret="", per_ip_per_min=kw.get("ip", 3), global_per_min=kw.get("glob", 10), daily_cap=kw.get("day", 100))
    app = FastAPI()
    llm = FakeLLM(script)
    app.include_router(create_router(FakeSource(TABLES), Bm25Index([]), llm, s))
    return TestClient(app), llm


GOOD = [tool_call("get_live_risk", {"pair": "USDC_DAI", "project": "curve"}),
        {"role": "assistant", "content": "The live risk score is 4.3575 [S1]."}]


def test_chat_ok_then_cached():
    c, llm = client(GOOD)
    r1 = c.post("/api/assistant/chat", json={"question": "Live risk for USDC_DAI curve?"}).json()
    r2 = c.post("/api/assistant/chat", json={"question": "  live RISK for usdc_dai curve? "}).json()
    assert r1["cached"] is False and r2["cached"] is True and len(llm.sent) == 2


def test_validation():
    c, _ = client([])
    assert c.post("/api/assistant/chat", json={"question": "x" * 501}).status_code == 422
    assert c.post("/api/assistant/chat", json={"question": "   "}).status_code == 422
    assert c.post("/api/assistant/chat", json={"question": "hi", "history": [{"role": "system", "content": "x"}]}).status_code == 422


def test_rate_limit_returns_429_with_retry_after():
    c, _ = client([], ip=1)
    assert c.post("/api/assistant/chat", json={"question": "Should I buy?"}).status_code == 200
    r = c.post("/api/assistant/chat", json={"question": "Should I buy?"})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_llm_failure_is_503_without_details():
    from assistant.llm import LLMError

    class Boom:
        async def complete(self, *a, **k):
            raise LLMError("http_500")

    s = Settings(model="m", api_key="SECRETKEY", proxy_secret="", per_ip_per_min=3, global_per_min=3, daily_cap=3)
    app = FastAPI()
    app.include_router(create_router(FakeSource(TABLES), Bm25Index([]), Boom(), s))
    r = TestClient(app).post("/api/assistant/chat", json={"question": "risk?"})
    assert r.status_code == 503 and "SECRETKEY" not in r.text and "500" not in r.text


def test_oversized_and_unsized_bodies_are_rejected_before_parsing():
    c, _ = client([])
    assert c.post("/api/assistant/chat", content=b'{"question":"' + b"x" * 9000 + b'"}',
                  headers={"content-type": "application/json"}).status_code == 413


def test_x_client_ip_is_trusted_only_with_the_shared_secret():
    s = Settings(model="m", api_key="k", proxy_secret="s3cret", per_ip_per_min=1, global_per_min=50, daily_cap=100)
    app = FastAPI()
    app.include_router(create_router(FakeSource(TABLES), Bm25Index([]), FakeLLM([]), s))
    c = TestClient(app)
    q = {"question": "Should I buy?"}
    # forged addresses without the secret all collapse onto the peer address -> second call limited
    assert c.post("/api/assistant/chat", json=q, headers={"x-client-ip": "1.1.1.1"}).status_code == 200
    assert c.post("/api/assistant/chat", json=q, headers={"x-client-ip": "2.2.2.2"}).status_code == 429
    # with the secret each forwarded visitor gets its own bucket
    h = {"x-proxy-secret": "s3cret"}
    assert c.post("/api/assistant/chat", json=q, headers={**h, "x-client-ip": "3.3.3.3"}).status_code == 200
    assert c.post("/api/assistant/chat", json=q, headers={**h, "x-client-ip": "4.4.4.4"}).status_code == 200
    assert c.post("/api/assistant/chat", json=q, headers={**h, "x-client-ip": "3.3.3.3"}).status_code == 429
