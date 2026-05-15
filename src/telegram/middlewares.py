import logging
import time

import redis.asyncio as aioredis

from src.config import settings

logger = logging.getLogger(__name__)

_redis_client = None


async def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


async def check_rate_limit(telegram_id: int, max_per_minute: int = 10) -> bool:
    """Rate limit por usuario. Devuelve True si puede continuar."""
    try:
        client = await _get_redis()
        key = f"ratelimit:{telegram_id}"
        now = time.time()
        window = 60

        pipe = client.pipeline()
        pipe.zremrangebyscore(key, "-inf", now - window)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now}": now})
        pipe.expire(key, window + 1)
        results = await pipe.execute()
        count = results[1]
        return count < max_per_minute
    except Exception as e:
        logger.warning("Rate limit check failed: %s", e)
        return True


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
