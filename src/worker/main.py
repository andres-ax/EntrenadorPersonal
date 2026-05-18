"""Worker arq para tareas asincronas: sync wearables, recalcular rankings, etc.

Run:
    arq src.worker.main.WorkerSettings
"""
from __future__ import annotations

import logging
from datetime import datetime

from arq.connections import RedisSettings
from arq.cron import cron

from src.config import settings
from src.log_setup import setup_logging
from src.worker.jobs_wearables import (
    refresh_tokens_expirados,
    sync_all_active_integrations,
    sync_single_integration,
)
from src.worker.jobs_comunidad import recalcular_rankings
from src.worker.jobs_procesado import procesar_datos_wearable_raw

setup_logging()

logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn.get_secret_value(),
            environment=settings.env,
            traces_sample_rate=0.05,
        )
        logger.info("Sentry inicializado en worker arq")
    except Exception:
        logger.exception("Sentry init fallo en worker arq")


async def startup(ctx) -> None:
    logger.info("Worker arq iniciado")


async def shutdown(ctx) -> None:
    logger.info("Worker arq detenido")


class WorkerSettings:
    """Configuracion del worker arq.

    Variables relevantes:
    - REDIS_URL: cola y resultados
    """

    redis_settings = RedisSettings.from_dsn(settings.redis_url_str)
    functions = [
        sync_single_integration,
        sync_all_active_integrations,
        refresh_tokens_expirados,
        procesar_datos_wearable_raw,
        recalcular_rankings,
    ]
    cron_jobs = [
        cron(sync_all_active_integrations, hour={0, 4, 8, 12, 16, 20}, minute=0),
        cron(refresh_tokens_expirados, hour=6, minute=0),
        cron(recalcular_rankings, minute={0, 30}),
        cron(procesar_datos_wearable_raw, minute={5, 15, 25, 35, 45, 55}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 5
    job_timeout = 600
