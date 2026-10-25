"""Data-source seam: the assistant only ever reads tables through this."""

from typing import Awaitable, Callable, Protocol

import httpx


class DataSource(Protocol):
    async def table(self, name: str, order: str | None = None) -> list[dict]: ...


class SupabaseSource:
    """Wraps backend/main.py's paged `_fetch_table` (single implementation of
    the 1000-row paging) instead of re-implementing it."""

    def __init__(self, fetch_table: Callable[..., Awaitable[list]], timeout: float = 10.0):
        self._fetch = fetch_table
        self._timeout = timeout

    async def table(self, name: str, order: str | None = None) -> list[dict]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await self._fetch(client, name, order=order)
