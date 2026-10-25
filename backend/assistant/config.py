"""Settings, all overridable by env var (documented in docs/SETUP.md)."""

import os
from dataclasses import dataclass

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    model: str
    api_key: str
    proxy_secret: str  # if set, x-client-ip is only trusted with a matching x-proxy-secret
    per_ip_per_min: int
    global_per_min: int
    daily_cap: int
    max_tool_rounds: int = 3  # rounds of tool use per question
    max_calls_per_round: int = 4  # the model sometimes issues parallel calls
    max_question_chars: int = 500
    max_body_bytes: int = 8192
    cache_ttl_seconds: int = 300
    llm_timeout_seconds: float = 20.0
    max_completion_tokens: int = 1024


def load_settings() -> Settings:
    return Settings(
        model=os.environ.get("ASSISTANT_MODEL", "openai/gpt-oss-20b"),
        api_key=os.environ.get("GROQ_API_KEY", ""),
        proxy_secret=os.environ.get("ASSISTANT_PROXY_SECRET", ""),
        # Defaults derive from the measured Groq limits for this account
        # (1000 requests/day, 8000 tokens/minute); see the plan, section 10.
        per_ip_per_min=_int("ASSISTANT_PER_IP_PER_MIN", 3),
        global_per_min=_int("ASSISTANT_GLOBAL_PER_MIN", 3),
        daily_cap=_int("ASSISTANT_DAILY_CAP", 200),
    )
