"""Reusable async HTTP foundation for academic providers.

Concepts kept from OpenDraft's `base.py` (retry, backoff, rate limiting, URL
safety); redesigned as an async client with tracing/quota hooks instead of
ported wholesale (see docs/OPENDRAFT_ADOPTION.md #9).
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from ranah_literature.errors import (
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)

TraceHook = Callable[[str, dict[str, object]], None]
RateLimitHook = Callable[[], Awaitable[None]]


def _noop_trace(event: str, data: dict[str, object]) -> None:
    return None


async def _noop_rate_limit() -> None:
    return None


class IntervalRateLimiter:
    """Minimum-interval quota mechanism: the shared `ProviderQuotaManager` every
    provider goes through, so no provider implements its own ad hoc throttling."""

    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval = min_interval_seconds
        self._lock = asyncio.Lock()
        self._last_call: float | None = None

    async def __call__(self) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            if self._last_call is not None:
                wait = self._min_interval - (now - self._last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
            self._last_call = loop.time()


class ProviderHTTPClient:
    """One instance per provider: its own base URL, headers, and retry policy."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        timeout_seconds: float = 15.0,
        max_retries: int = 3,
        backoff_base_seconds: float = 1.0,
        rate_limit_hook: RateLimitHook = _noop_rate_limit,
        trace_hook: TraceHook = _noop_trace,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url, headers=headers or {}, params=params, timeout=timeout_seconds
        )
        self._max_retries = max_retries
        self._backoff_base = backoff_base_seconds
        self._rate_limit = rate_limit_hook
        self._trace = trace_hook

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            await self._rate_limit()
            self._trace("provider.request", {"path": path, "attempt": attempt})
            try:
                response = await self._client.get(path, params=params)
            except httpx.TimeoutException as exc:
                last_error = exc
                await self._backoff(attempt)
                continue
            except httpx.ConnectError as exc:
                last_error = exc
                await self._backoff(attempt)
                continue

            if response.status_code == 401 or response.status_code == 403:
                raise ProviderAuthError(f"{path} -> {response.status_code}")
            if response.status_code == 404:
                raise ProviderNotFoundError(f"{path} -> 404")
            if response.status_code == 429:
                last_error = ProviderRateLimitError(f"{path} -> 429")
                await self._backoff(attempt)
                continue
            if response.status_code >= 500:
                last_error = ProviderResponseError(f"{path} -> {response.status_code}")
                await self._backoff(attempt)
                continue
            if response.status_code >= 400:
                raise ProviderResponseError(f"{path} -> {response.status_code}")

            self._trace("provider.response", {"path": path, "attempt": attempt})
            result: dict[str, Any] = response.json()
            return result

        assert last_error is not None
        if isinstance(last_error, httpx.TimeoutException):
            raise ProviderTimeoutError(str(last_error)) from last_error
        if isinstance(last_error, ProviderRateLimitError | ProviderResponseError):
            raise last_error
        raise ProviderResponseError(str(last_error)) from last_error

    async def _backoff(self, attempt: int) -> None:
        self._trace("provider.retry", {"attempt": attempt})
        await asyncio.sleep(min(self._backoff_base * 2**attempt, 10))
