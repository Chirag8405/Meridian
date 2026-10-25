"""POST /api/assistant/chat. Mounted by backend/main.py."""

import hmac
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from assistant.chat import DataUnavailable, answer_question
from assistant.config import Settings
from assistant.data import DataSource
from assistant.llm import LLMError
from assistant.ratelimit import RateLimiter
from assistant.retrieval import Bm25Index

UNAVAILABLE = "The assistant is unavailable right now. The rest of the dashboard is unaffected."
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class Turn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=500)


class ChatRequest(BaseModel):
    question: str = Field(max_length=500)
    history: list[Turn] = Field(default_factory=list, max_length=4)


def create_router(src: DataSource, index: Bm25Index, llm, settings: Settings) -> APIRouter:
    router = APIRouter()
    limiter = RateLimiter(settings.per_ip_per_min, settings.global_per_min, settings.daily_cap)
    cache: dict[tuple, tuple[float, dict]] = {}

    async def data_version() -> str:
        meta = await src.table("metadata")
        events = await src.table("recent_swap_events", order="observed_at.desc,event_id.desc")
        return f"{meta[0].get('exported_at') if meta else ''}|{events[0]['observed_at'] if events else ''}"

    async def limit_body(request: Request) -> None:
        """Reject oversized bodies before pydantic parses them (a forged huge body would otherwise
        be buffered in memory). Clients that send JSON always set Content-Length."""
        length = request.headers.get("content-length")
        if length is None or not length.isdigit():
            raise HTTPException(status_code=411, detail="Content-Length required")
        if int(length) > settings.max_body_bytes:
            raise HTTPException(status_code=413, detail="Request too large")

    def client_id(request: Request) -> str:
        """The visitor address forwarded by the Next.js proxy, trusted only when the shared secret
        matches (if one is configured); otherwise the direct peer address."""
        forwarded = request.headers.get("x-client-ip")
        if forwarded and (
            not settings.proxy_secret
            or hmac.compare_digest(request.headers.get("x-proxy-secret", ""), settings.proxy_secret)
        ):
            return forwarded[:64]
        return request.client.host if request.client else "unknown"

    @router.post("/api/assistant/chat", dependencies=[Depends(limit_body)])
    async def chat(req: ChatRequest, request: Request):
        question = _CONTROL.sub(" ", req.question).strip()
        if not question:
            raise HTTPException(status_code=422, detail="question must not be empty")
        client = client_id(request)

        ok, reason, retry_after = limiter.check(client)
        if not ok:
            msg = ("The assistant has reached its daily limit and is resting. Please try again tomorrow."
                   if reason == "daily" else "Too many questions right now. Please wait a moment and try again.")
            raise HTTPException(status_code=429, detail=msg, headers={"Retry-After": str(retry_after)})

        key = None
        if not req.history:
            try:
                key = (" ".join(question.lower().split()), await data_version())
            except Exception:
                key = None
            hit = cache.get(key) if key else None
            if hit and time.time() - hit[0] < settings.cache_ttl_seconds:
                return {**hit[1], "cached": True}

        try:
            result = await answer_question(
                question, [t.model_dump() for t in req.history], src, index, llm, settings
            )
        except DataUnavailable:
            print("assistant: data source unavailable")
            raise HTTPException(status_code=503, detail=UNAVAILABLE) from None
        except LLMError as exc:
            print(f"assistant: llm failure: {exc}")  # reason code only; never the key or body
            raise HTTPException(status_code=503, detail=UNAVAILABLE) from None
        except Exception as exc:
            print(f"assistant: unexpected failure: {type(exc).__name__}")
            raise HTTPException(status_code=503, detail=UNAVAILABLE) from None
        if key and not result["refused"]:
            if len(cache) >= 200:
                cache.clear()  # bounded memory; entries expire in minutes anyway
            cache[key] = (time.time(), result)
        return {**result, "cached": False}

    return router
