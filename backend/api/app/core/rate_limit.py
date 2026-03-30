"""
Redis-backed rate limiter.

Uses a simple fixed-window counter approach:
- INCR on every request to increment the count.
- EXPIRE only on the first request (count == 1) to set the window TTL.
This prevents the TTL-reset bug where a client making sparse requests would
keep the key alive indefinitely.
"""

import logging
from typing import Annotated

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IP_LIMIT = 500  # requests per window — Layer 2: public endpoints
_IP_WINDOW_SECONDS = 60  # 1-minute window

_TOKEN_LIMIT = 60  # requests per window — Layer 3: authenticated endpoints
_TOKEN_WINDOW_SECONDS = 60  # 1-minute window


# ---------------------------------------------------------------------------
# Core limiter
# ---------------------------------------------------------------------------


async def _check_rate_limit(
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """
    Increment the rate-limit counter for ``key`` and raise 429 if exceeded.

    Uses a two-step Redis approach:
    1. INCR the key to get the current request count.
    2. EXPIRE only when count == 1 (first request in a new window) to set the TTL.

    This avoids the TTL-reset bug where calling EXPIRE on every request would
    extend the window indefinitely for sparse-but-persistent clients.
    """
    try:
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, window_seconds)
    except RedisError:
        # Fail open: if Redis is unavailable we allow the request rather than
        # blocking all users. The failure is logged for observability.
        logger.warning("Rate-limit Redis check failed; allowing request (key=%s)", key)
        return

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too Many Requests",
        )


# ---------------------------------------------------------------------------
# Layer 2 – IP-based (public endpoints)
# ---------------------------------------------------------------------------

IP_RATE_LIMIT = _IP_LIMIT
IP_WINDOW_SECONDS = _IP_WINDOW_SECONDS


async def check_ip_rate_limit(request: Request) -> None:
    """
    Dependency that enforces the Layer 2 IP-based rate limit on public endpoints.

    Reads the real client IP from the X-Forwarded-For header when the API is
    deployed behind a reverse proxy (e.g. Docker + nginx). Falls back to
    request.client.host for direct connections (local dev).
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # Leftmost IP is the original client; proxy chain follows.
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:ip:{client_ip}"
    await _check_rate_limit(key, IP_RATE_LIMIT, IP_WINDOW_SECONDS)


IpRateLimitDep = Annotated[None, check_ip_rate_limit]


# ---------------------------------------------------------------------------
# Layer 3 – Token-based (authenticated endpoints)
# ---------------------------------------------------------------------------

TOKEN_RATE_LIMIT = _TOKEN_LIMIT
TOKEN_WINDOW_SECONDS = _TOKEN_WINDOW_SECONDS


async def check_token_rate_limit(
    request: Request,
    subject_id: str,
) -> None:
    """
    Enforces the Layer 3 token-based rate limit for an authenticated client.

    Args:
        subject_id: The user_id or kiosk_id extracted from the JWT/device token.
    """
    key = f"ratelimit:token:{subject_id}"
    await _check_rate_limit(key, TOKEN_RATE_LIMIT, TOKEN_WINDOW_SECONDS)
