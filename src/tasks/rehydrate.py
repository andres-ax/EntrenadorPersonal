"""Rehydrate: carga recordatorios activos desde Postgres a Redis al boot."""
from __future__ import annotations

import logging

from src.config import settings
from src.db.repository import listar_recordatorios_activos_global
from src.tasks.scheduling import schedule_recordatorio_task

logger = logging.getLogger(__name__)


async def rehydrate_tasks_from_db() -> int:
    if not settings.use_redis_task_queue:
        return 0
    try:
        recordatorios = await listar_recordatorios_activos_global()
    except Exception:
        logger.exception("Error rehydrate recordatorios")
        return 0
    total = 0
    for rec in recordatorios:
        try:
            tid = await schedule_recordatorio_task(rec)
            if tid:
                total += 1
        except Exception:
            logger.exception("Error rehydrate recordatorio %s", rec.id)
    logger.info("Rehydrate: %d recordatorios en Redis", total)
    return total
