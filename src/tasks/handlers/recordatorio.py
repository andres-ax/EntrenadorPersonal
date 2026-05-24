"""Handler recordatorio personalizado."""
from __future__ import annotations

import logging

from telegram.constants import ParseMode

from src.db.repository import marcar_recordatorio_enviado
from src.services.proactive_limit import registrar_envio_proactivo
from src.tasks.scheduling import schedule_recordatorio_task
from src.telegram.scheduler import _enviar_safe

logger = logging.getLogger(__name__)


async def handle(bot, doc: dict) -> None:
    payload = doc.get("payload") or {}
    telegram_id = int(doc.get("telegram_id") or 0)
    mensaje = payload.get("mensaje") or ""
    rid = payload.get("recordatorio_id")
    if not telegram_id or not mensaje:
        return
    await _enviar_safe(
        bot, telegram_id, f"<b>Recordatorio:</b> {mensaje}", parse_mode=ParseMode.HTML
    )
    await registrar_envio_proactivo(telegram_id)
    if rid is not None:
        rec = await marcar_recordatorio_enviado(int(rid))
        if rec is not None and rec.activo and rec.dias_semana:
            await schedule_recordatorio_task(rec)
