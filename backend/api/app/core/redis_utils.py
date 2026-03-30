"""Centralised Redis distributed-lock utilities.

All workers that need mutual exclusion must use `acquire_distributed_lock`
to ensure only one instance runs a critical section at a time.
"""

import logging

from app.db.redis import redis_client

logger = logging.getLogger(__name__)


async def acquire_distributed_lock(
    lock_key: str,
    ttl_seconds: int,
) -> bool:
    """
    Atomically acquire a Redis-backed distributed lock using SET NX EX.

    Args:
        lock_key:  Unique name for the lock (e.g. "lock:overdue-worker").
        ttl_seconds:  Time-to-live. The lock is automatically released if the
                     holder crashes. Must be shorter than the run interval so
                     that a crashed holder does not block the next scheduled run.

    Returns:
        True  — lock acquired (this instance should run the critical section).
        False — lock held by another instance (skip this cycle).
    """
    acquired = await redis_client.set(
        lock_key,
        "1",
        nx=True,
        ex=ttl_seconds,
    )
    if acquired:
        logger.debug("Acquired distributed lock: %s (ttl=%ds)", lock_key, ttl_seconds)
    else:
        logger.debug("Failed to acquire distributed lock (already held): %s", lock_key)
    return bool(acquired)
