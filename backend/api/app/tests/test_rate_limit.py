"""
Tests for the Redis-backed rate limiter (app/core/rate_limit.py).
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request

from app.core.rate_limit import (
    _check_rate_limit,
    check_ip_rate_limit,
    check_token_rate_limit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_request(
    client_host: str | None = "192.168.1.1",
    headers: dict[str, str] | None = None,
) -> Request:
    """Build a real FastAPI Request from an ASGI scope dict (Pylance-friendly)."""
    scope = {
        "type": "http",
        "client": (client_host, 12345) if client_host else None,
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# _check_rate_limit
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_rate_limit_allows_request_under_limit():
    """When Redis returns count=1 (first request) the function must pass."""
    with patch("app.core.rate_limit.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        # Must not raise
        await _check_rate_limit("ratelimit:test:key1", limit=10, window_seconds=60)
        mock_redis.incr.assert_awaited_once_with("ratelimit:test:key1")
        mock_redis.expire.assert_awaited_once_with("ratelimit:test:key1", 60)


@pytest.mark.anyio
async def test_check_rate_limit_raises_429_when_limit_exceeded():
    """When Redis returns count > limit, HTTPException 429 must be raised."""
    with patch("app.core.rate_limit.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=11)  # count = 11 > limit = 10
        mock_redis.expire = AsyncMock()  # should NOT be called
        with pytest.raises(HTTPException) as exc_info:
            await _check_rate_limit("ratelimit:test:key2", limit=10, window_seconds=60)
        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Too Many Requests"
        mock_redis.expire.assert_not_awaited()


@pytest.mark.anyio
async def test_check_rate_limit_fails_open_on_redis_error():
    """If Redis is unavailable, the limiter must allow the request (fail-open)."""
    from redis.exceptions import RedisError

    with patch("app.core.rate_limit.redis_client") as mock_redis:
        mock_redis.incr.side_effect = RedisError("connection refused")
        # Must NOT raise — fail-open
        await _check_rate_limit("ratelimit:test:key3", limit=10, window_seconds=60)


@pytest.mark.anyio
async def test_check_rate_limit_at_boundary():
    """When count equals limit exactly, the request is still allowed."""
    with patch("app.core.rate_limit.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=10)  # count == limit
        mock_redis.expire = AsyncMock()  # should NOT be called
        # Must NOT raise — limit is inclusive
        await _check_rate_limit("ratelimit:test:key4", limit=10, window_seconds=60)
        mock_redis.expire.assert_not_awaited()


# ---------------------------------------------------------------------------
# check_ip_rate_limit
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_ip_rate_limit_uses_x_forwarded_for():
    """When behind a proxy, X-Forwarded-For must be used as the rate-limit key."""
    with patch("app.core.rate_limit.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        request = make_mock_request(
            client_host="10.255.0.1",
            headers={"X-Forwarded-For": "203.0.113.50, 10.255.0.1, 172.17.0.1"},
        )
        await check_ip_rate_limit(request)
        # Leftmost IP is the original client
        mock_redis.incr.assert_awaited_once_with("ratelimit:ip:203.0.113.50")


@pytest.mark.anyio
async def test_check_ip_rate_limit_falls_back_to_client_host():
    """Without X-Forwarded-For, request.client.host must be used."""
    with patch("app.core.rate_limit.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        request = make_mock_request(client_host="10.0.0.5", headers={})
        await check_ip_rate_limit(request)
        mock_redis.incr.assert_awaited_once_with("ratelimit:ip:10.0.0.5")


@pytest.mark.anyio
async def test_check_ip_rate_limit_unknown_ip_handled_gracefully():
    """If request.client is None, the key should use 'unknown'."""
    with patch("app.core.rate_limit.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        request = make_mock_request(client_host=None, headers={})
        await check_ip_rate_limit(request)
        mock_redis.incr.assert_awaited_once_with("ratelimit:ip:unknown")


# ---------------------------------------------------------------------------
# check_token_rate_limit
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_token_rate_limit_uses_subject_id_as_key():
    """The rate-limit key must include the subject (user/kiosk) ID."""
    with patch("app.core.rate_limit.redis_client") as mock_redis:
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)
        user_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        await check_token_rate_limit(
            make_mock_request(client_host="192.168.1.1"),
            user_id,
        )
        mock_redis.incr.assert_awaited_once_with(f"ratelimit:token:{user_id}")
