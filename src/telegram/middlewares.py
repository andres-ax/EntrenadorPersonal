"""Rate limit por usuario usando Redis sorted sets (sliding window)."""
from __future__ import annotations

import logging
import time

from src.cache import get_redis
from src.config import settings

logger = logging.getLogger(__name__)


async def check_rate_limit(
    telegram_id: int, max_per_minute: int | None = None
) -> bool:
    """Devuelve True si el usuario puede continuar.

    Sliding window de 60s con sorted set por usuario. Si Redis falla,
    devuelve True (fail-open) para no bloquear al usuario.
    """
    limite = max_per_minute or settings.rate_limit_per_minute
    try:
        client = await get_redis()
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
        return count < limite
    except Exception as e:
        logger.warning("Rate limit check failed: %s", e)
        return True


# Re-export por compatibilidad con código previo (handlers/main).
from src.cache import close_redis  # noqa: E402,F401
