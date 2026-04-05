"""Shared idempotency guard using Redis SET NX EX pattern.

Prevents duplicate processing of POST/PATCH requests that share the same
idempotency key. Uses SET NX EX (set-if-not-exists with TTL) for atomic
acquisition — the first request with a given key wins; concurrent duplicates
receive 409 Conflict.
"""

import logging

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.db.redis import redis_client

logger = logging.getLogger(__name__)

_IDEMPOTENCY_TTL_SECONDS = 86400  # 24 hours


async def _guard_idempotency(idempotency_key: str) -> None:
    """
    Atomically claim an idempotency key in Redis.

    Raises HTTPException 409 if the key already exists (duplicate request).
    The key expires after _IDEMPOTENCY_TTL_SECONDS to prevent unbounded growth.
    """
    redis_key = f"idempotency:{idempotency_key}"
    try:
        was_set = await redis_client.set(
            redis_key, "processing", ex=_IDEMPOTENCY_TTL_SECONDS, nx=True
        )
    except (TimeoutError, RedisError) as exc:
        logger.warning(
            "Redis unavailable during idempotency check for key: %s", redis_key
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable. Please try again later.",
        ) from exc

    if not was_set:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Duplicate request with this idempotency key is already being processed or has completed.",
        )


async def release_idempotency_key(idempotency_key: str) -> None:
    """
    Remove a consumed idempotency key from Redis.

    Called when an endpoint needs to unblock a key after a safe-to-retry
    failure (e.g., 503 hardware unreachable). Burns the key immediately so
    a subsequent retry with the same key can re-acquire it.
    """
    redis_key = f"idempotency:{idempotency_key}"
    try:
        await redis_client.delete(redis_key)
    except (TimeoutError, RedisError):
        # Fail silently to avoid masking the primary exception during rollbacks.
        logger.exception(
            "Failed to release idempotency key (Redis unavailable). Key: %s", redis_key
        )
