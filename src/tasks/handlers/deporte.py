"""Handler recordatorio sesión skill (deportes urbanos)."""
from __future__ import annotations

from src.telegram.jobs_deportes import enviar_recordar_sesion_skill


async def handle(bot, doc: dict) -> None:
    telegram_id = int(doc.get("telegram_id") or 0)
    if telegram_id:
        await enviar_recordar_sesion_skill(bot, telegram_id)
