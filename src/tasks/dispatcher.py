"""Dispatcher: claim atómico + ejecución de handlers."""
from __future__ import annotations

import logging

from src.config import settings
from src.tasks.audit import log_task_audit
from src.tasks.handlers import get_handler
from src.tasks.queue import (
    acquire_dispatcher_lock,
    claim_due_tasks,
    complete_task,
    fail_task,
    release_dispatcher_lock,
)
from src.services.proactive_limit import puede_enviar_proactivo

logger = logging.getLogger(__name__)


async def dispatch_due_tasks(bot) -> int:
    """Claim y ejecuta tareas vencidas. Devuelve cantidad procesada."""
    if not settings.use_redis_task_queue:
        return 0
    if not await acquire_dispatcher_lock():
        return 0
    processed = 0
    try:
        tasks = await claim_due_tasks(limit=25)
        for doc in tasks:
            task_id = doc.get("id", "")
            task_type = doc.get("type", "")
            telegram_id = int(doc.get("telegram_id") or 0)
            try:
                await log_task_audit(
                    task_id=task_id,
                    telegram_id=telegram_id,
                    task_type=task_type,
                    action="claimed",
                    payload_snapshot=doc.get("payload"),
                )
                if task_type != "recordatorio" and not await puede_enviar_proactivo(telegram_id):
                    await log_task_audit(
                        task_id=task_id,
                        telegram_id=telegram_id,
                        task_type=task_type,
                        action="skipped_cap",
                    )
                    await complete_task(task_id, {"skipped": "cap"})
                    continue
                handler = get_handler(task_type)
                if handler is None:
                    await fail_task(task_id, f"handler desconocido: {task_type}")
                    await log_task_audit(
                        task_id=task_id,
                        telegram_id=telegram_id,
                        task_type=task_type,
                        action="failed",
                        error=f"handler desconocido: {task_type}",
                    )
                    continue
                await handler(bot, doc)
                await complete_task(task_id)
                await log_task_audit(
                    task_id=task_id,
                    telegram_id=telegram_id,
                    task_type=task_type,
                    action="sent",
                )
                processed += 1
            except Exception as exc:
                logger.exception(
                    "Error dispatch task_id=%s type=%s uid=%s",
                    task_id,
                    task_type,
                    telegram_id,
                )
                await fail_task(task_id, str(exc))
                await log_task_audit(
                    task_id=task_id,
                    telegram_id=telegram_id,
                    task_type=task_type,
                    action="failed",
                    error=str(exc),
                )
    finally:
        await release_dispatcher_lock()
    return processed
