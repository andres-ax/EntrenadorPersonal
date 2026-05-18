"""Cuotas de minutos Realtime por tier, contadas en Redis por mes."""
from __future__ import annotations

import logging
from datetime import datetime

from src.cache import get_redis
from src.db.models import PlanSuscripcion
from src.db.repository import obtener_plan_actual

logger = logging.getLogger(__name__)

CUOTAS_MIN_POR_TIER = {
    PlanSuscripcion.FREE: 0,
    PlanSuscripcion.STARTER: 5,
    PlanSuscripcion.PRO: 30,
    PlanSuscripcion.ELITE: 120,
    PlanSuscripcion.LIFETIME: 120,
}

HARD_CAP_USD_MES = 10.0


def _key(uid: int) -> str:
    ahora = datetime.utcnow()
    return f"realtime_uso:{uid}:{ahora.year:04d}{ahora.month:02d}"


async def cuota_total_segundos(telegram_id: int) -> int:
    plan = await obtener_plan_actual(telegram_id)
    return CUOTAS_MIN_POR_TIER.get(plan, 0) * 60


async def consumido_segundos(telegram_id: int) -> int:
    client = await get_redis()
    val = await client.get(_key(telegram_id))
    try:
        return int(val) if val else 0
    except (TypeError, ValueError):
        return 0


async def disponible_segundos(telegram_id: int) -> int:
    total = await cuota_total_segundos(telegram_id)
    consumido = await consumido_segundos(telegram_id)
    return max(0, total - consumido)


async def consumir_segundos(telegram_id: int, segundos: int) -> int:
    """Incrementa contador. Devuelve segundos restantes."""
    if segundos <= 0:
        return await disponible_segundos(telegram_id)
    client = await get_redis()
    key = _key(telegram_id)
    nuevo = await client.incrby(key, segundos)
    await client.expire(key, 35 * 24 * 3600)
    restantes = max(0, (await cuota_total_segundos(telegram_id)) - int(nuevo))
    return restantes
