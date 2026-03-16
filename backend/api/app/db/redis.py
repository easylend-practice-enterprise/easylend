from redis.asyncio import Redis

from app.core.config import settings

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_redis_connection():
    try:
        await redis_client.ping()  # type: ignore
        print("Succesvol verbonden met Redis Cache.")
    except Exception as e:
        print(f"Kan niet verbinden met Redis: {e}")


async def store_refresh_token(user_id: str, jti: str, expires_in_seconds: int):
    """
    Slaat een geldige refresh token op in de Redis whitelist.
    """
    await redis_client.setex(f"refresh:{user_id}:{jti}", expires_in_seconds, "valid")


async def is_refresh_token_valid(user_id: str, jti: str) -> bool:
    """
    Controleert of een refresh token nog in de Redis whitelist staat.
    """
    return await redis_client.exists(f"refresh:{user_id}:{jti}") > 0


async def revoke_refresh_token(user_id: str, jti: str) -> bool:
    """
    Trekt één specifieke refresh token in.
    Geeft True terug als de token daadwerkelijk bestond en is verwijderd.
    """
    result = await redis_client.delete(f"refresh:{user_id}:{jti}")
    return result > 0


async def revoke_all_refresh_tokens(user_id: str):
    """
    Verwijdert alle actieve sessies van een gebruiker (overal uitloggen).
    """
    cursor = 0
    while True:
        cursor, keys = await redis_client.scan(cursor, match=f"refresh:{user_id}:*")
        if keys:
            await redis_client.delete(*keys)
        if cursor == 0:
            break
