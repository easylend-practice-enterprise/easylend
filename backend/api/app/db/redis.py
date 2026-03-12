from redis.asyncio import Redis

from app.core.config import settings

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_redis_connection():
    try:
        await redis_client.ping()  # type: ignore
        print("Succesvol verbonden met Redis Cache.")
    except Exception as e:
        print(f"Kan niet verbinden met Redis: {e}")


async def set_refresh_token(user_id: str, jti: str, expires_in: int = 604800):
    """
    Markeert een sessie als actief in Redis op basis van user_id en jti (multi-session).
    """
    await redis_client.set(f"refresh:{user_id}:{jti}", "active", ex=expires_in)


async def verify_refresh_token_exists(user_id: str, jti: str) -> bool:
    """
    Controleert of een specifieke sessie nog actief is.
    """
    result = await redis_client.exists(f"refresh:{user_id}:{jti}")
    return result > 0


async def revoke_refresh_token(user_id: str, jti: str):
    """
    Verwijdert één specifieke sessie (logout van één apparaat).
    """
    await redis_client.delete(f"refresh:{user_id}:{jti}")


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
