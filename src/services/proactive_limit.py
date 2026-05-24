"""Cap diario de mensajes proactivos por usuario (Redis)."""
from __future__ import annotations

import logging

from src.cache import get_redis
from src.config import settings
from src.timezone_utils import fecha_hoy_usuario

logger = logging.getLogger(__name__)

_PROACTIVE_KEY = "proactive_count:{}:{}"
_HIDRATACION_DEDUP_KEY = "hidratacion_sent:{}:{}"


async def puede_enviar_proactivo(telegram_id: int) -> bool:
    """True si el usuario no superó el cap diario de mensajes proactivos."""
    try:
        hoy = await fecha_hoy_usuario(telegram_id)
        client = await get_redis()
        key = _PROACTIVE_KEY.format(telegram_id, hoy.isoformat())
        count = int(await client.get(key) or 0)
        return count < settings.max_proactive_msgs_per_day
    except Exception:
        logger.exception("Error leyendo cap proactivo uid=%s", telegram_id)
        return True


async def registrar_envio_proactivo(telegram_id: int) -> int:
    """Incrementa contador y devuelve el nuevo total del día."""
    hoy = await fecha_hoy_usuario(telegram_id)
    client = await get_redis()
    key = _PROACTIVE_KEY.format(telegram_id, hoy.isoformat())
    new_val = await client.incr(key)
    if new_val == 1:
        await client.expire(key, 60 * 60 * 48)
    return int(new_val)


async def hidratacion_enviada_reciente(telegram_id: int) -> bool:
    """True si ya se envió recordatorio de hidratación en la última hora."""
    try:
        hoy = await fecha_hoy_usuario(telegram_id)
        client = await get_redis()
        key = _HIDRATACION_DEDUP_KEY.format(telegram_id, hoy.isoformat())
        return bool(await client.get(key))
    except Exception:
        return False


async def marcar_hidratacion_enviada(telegram_id: int) -> None:
    hoy = await fecha_hoy_usuario(telegram_id)
    client = await get_redis()
    key = _HIDRATACION_DEDUP_KEY.format(telegram_id, hoy.isoformat())
    await client.setex(key, 3600, "1")
