import redis.asyncio as aioredis
from app.core.config import settings

redis_client: aioredis.Redis = aioredis.from_url(
    settings.REDIS_URL,
    encoding="utf-8",
    decode_responses=True,
)


async def get_cached(key: str) -> str | None:
    return await redis_client.get(key)


async def set_cached(key: str, value: str, ttl_seconds: int = 300):
    await redis_client.setex(key, ttl_seconds, value)


async def invalidate(key: str):
    await redis_client.delete(key)
