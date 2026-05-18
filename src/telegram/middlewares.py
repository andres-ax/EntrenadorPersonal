"""Rate limit y cuota diaria por usuario usando Redis."""
from __future__ import annotations

import logging
import time
from datetime import date

from src.cache import get_redis
from src.config import settings
from src.db.models import PlanSuscripcion
from src.db.repository import obtener_plan_actual

logger = logging.getLogger(__name__)

FREE_DAILY_LIMIT = settings.free_daily_msg_limit


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


async def check_rate_limit_ip(ip: str, max_per_minute: int = 5) -> bool:
    """Rate limit por IP para endpoints HTTP (auth, magic-link, etc.).

    Misma logica Redis sliding window que check_rate_limit.
    Fail-open si Redis falla.
    """
    try:
        client = await get_redis()
        key = f"ratelimit:ip:{ip}"
        now = time.time()
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, "-inf", now - 60)
        pipe.zcard(key)
        pipe.zadd(key, {f"{now}": now})
        pipe.expire(key, 61)
        results = await pipe.execute()
        return results[1] < max_per_minute
    except Exception as e:
        logger.warning("IP rate limit check failed: %s", e)
        return True


async def check_daily_quota(
    telegram_id: int,
) -> tuple[bool, int, int]:
    """Verifica cuota diaria de mensajes solo para usuarios FREE.

    Planes pagos no tienen limite diario.

    Returns:
        (puede_continuar, mensajes_usados, limite)
        limite=0 significa ilimitado.
    """
    try:
        plan = await obtener_plan_actual(telegram_id)
        if plan != PlanSuscripcion.FREE:
            return True, 0, 0

        client = await get_redis()
        hoy = date.today().isoformat()
        key = f"daily_msg:{telegram_id}:{hoy}"

        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 86400)
        results = await pipe.execute()
        usado = results[0]

        return usado <= FREE_DAILY_LIMIT, usado, FREE_DAILY_LIMIT
    except Exception as e:
        logger.warning("Daily quota check failed: %s", e)
        return True, 0, 0


# Re-export por compatibilidad con código previo (handlers/main).
from src.cache import close_redis  # noqa: E402,F401
