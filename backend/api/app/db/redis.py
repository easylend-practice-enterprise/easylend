import logging

from redis.asyncio import Redis

from app.core.config import settings

logger = logging.getLogger(__name__)

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_redis_connection():
    try:
        await redis_client.ping()
        logger.info("Successfully connected to Redis Cache.")
    except Exception as exc:
        logger.warning("Could not connect to Redis: %s", exc)


async def store_refresh_token(user_id: str, jti: str, expires_in_seconds: int):
    """
    Stores a valid refresh token in the Redis whitelist.
    """
    if expires_in_seconds <= 0:
        raise ValueError("expires_in_seconds must be a positive integer.")
    await redis_client.setex(f"refresh:{user_id}:{jti}", expires_in_seconds, "valid")


async def is_refresh_token_valid(user_id: str, jti: str) -> bool:
    """
    Checks whether a refresh token is still present in the Redis whitelist.
    """
    return await redis_client.exists(f"refresh:{user_id}:{jti}") > 0


async def revoke_refresh_token(user_id: str, jti: str) -> bool:
    """
    Revokes a single specific refresh token.
    Returns True if the token actually existed and was deleted.
    """
    result = await redis_client.delete(f"refresh:{user_id}:{jti}")
    return result > 0


async def revoke_all_refresh_tokens(user_id: str):
    """
    Revokes all active sessions for a user (global sign-out).
    """
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match=f"refresh:{user_id}:*")
        if keys:
            await redis_client.delete(*keys)
        if cursor == 0:
            break
