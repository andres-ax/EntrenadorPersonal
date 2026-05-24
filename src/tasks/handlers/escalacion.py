"""Handler escalación por tipo."""
from __future__ import annotations

from src.telegram.escalation import ejecutar_escalacion


async def handle(bot, doc: dict) -> None:
    payload = doc.get("payload") or {}
    telegram_id = int(doc.get("telegram_id") or 0)
    tipo = payload.get("tipo_accion", "entreno")
    level = int(payload.get("level") or 1)
    freq = int(payload.get("freq") or 3)
    streak = int(payload.get("streak") or 0)
    if telegram_id:
        await ejecutar_escalacion(
            bot,
            telegram_id,
            tipo,
            target_level=level,
            freq=freq,
            streak=streak,
        )
