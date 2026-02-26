from redis.asyncio import Redis
from app.core.config import settings

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_redis_connection():
    try:
        await redis_client.ping()  # type: ignore
        print("✅ Succesvol verbonden met Redis Cache!")
    except Exception as e:
        print(f"❌ Kan niet verbinden met Redis: {e}")


async def set_refresh_token(user_id: str, token: str, expires_in: int = 604800):
    """
    Slaat een refresh token op in Redis.
    Standaard vervaltijd is 7 dagen (604800 seconden).
    """
    # We gebruiken een logische sleutel, bijv. "refresh_token:123"
    await redis_client.set(f"refresh_token:{user_id}", token, ex=expires_in)


async def get_refresh_token(user_id: str) -> str | None:
    """
    Haalt het refresh token van een specifieke gebruiker op.
    Geeft None terug als het token niet bestaat of verlopen is.
    """
    return await redis_client.get(f"refresh_token:{user_id}")


async def delete_refresh_token(user_id: str):
    """
    Verwijdert het refresh token (wordt gebruikt bij uitloggen).
    """
    await redis_client.delete(f"refresh_token:{user_id}")
