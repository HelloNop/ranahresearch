"""EPIC-008 acceptance tests for the shared provider HTTP foundation. No network: httpx's
MockTransport stands in for a real provider."""

import httpx
import pytest
from ranah_literature.errors import (
    ProviderAuthError,
    ProviderNotFoundError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from ranah_literature.http import ProviderHTTPClient


def _client(handler: httpx.MockTransport, **kwargs: object) -> ProviderHTTPClient:
    client = ProviderHTTPClient("https://example.test", backoff_base_seconds=0.01, **kwargs)  # type: ignore[arg-type]
    client._client = httpx.AsyncClient(base_url="https://example.test", transport=handler)
    return client


async def test_get_json_returns_body_on_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    client = _client(httpx.MockTransport(handler))
    assert await client.get_json("/works") == {"ok": True}


async def test_404_becomes_not_found_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = _client(httpx.MockTransport(handler))
    with pytest.raises(ProviderNotFoundError):
        await client.get_json("/works/missing")


async def test_401_becomes_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    client = _client(httpx.MockTransport(handler))
    with pytest.raises(ProviderAuthError):
        await client.get_json("/works")


async def test_429_retries_then_raises_rate_limit_error() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(429)

    client = _client(httpx.MockTransport(handler), max_retries=2)
    with pytest.raises(ProviderRateLimitError):
        await client.get_json("/works")
    assert calls["count"] == 2


async def test_500_retries_then_raises_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _client(httpx.MockTransport(handler), max_retries=2)
    with pytest.raises(ProviderResponseError):
        await client.get_json("/works")


async def test_timeout_becomes_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("boom")

    client = _client(httpx.MockTransport(handler), max_retries=1)
    with pytest.raises(ProviderTimeoutError):
        await client.get_json("/works")


async def test_400_is_not_retried() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        return httpx.Response(400)

    client = _client(httpx.MockTransport(handler), max_retries=3)
    with pytest.raises(ProviderResponseError):
        await client.get_json("/works")
    assert calls["count"] == 1
