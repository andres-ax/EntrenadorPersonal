"""Handler recordatorio hidratación."""
from __future__ import annotations

from src.telegram.scheduler import enviar_recordatorio_hidratacion_usuario


async def handle(bot, doc: dict) -> None:
    telegram_id = int(doc.get("telegram_id") or 0)
    if telegram_id:
        await enviar_recordatorio_hidratacion_usuario(bot, telegram_id)
