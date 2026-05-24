"""Auditoría append-only de tareas en Postgres."""
from __future__ import annotations

import logging
from typing import Any

from src.db.connection import async_session_factory
from src.db.models import TaskAuditLog

logger = logging.getLogger(__name__)


async def log_task_audit(
    *,
    task_id: str,
    telegram_id: int,
    task_type: str,
    action: str,
    payload_snapshot: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    try:
        async with async_session_factory() as session:
            row = TaskAuditLog(
                task_id=task_id,
                telegram_id=telegram_id,
                task_type=task_type,
                action=action,
                payload_snapshot=payload_snapshot,
                error=(error[:500] if error else None),
            )
            session.add(row)
            await session.commit()
    except Exception:
        logger.exception(
            "Error audit task_id=%s type=%s action=%s", task_id, task_type, action
        )
