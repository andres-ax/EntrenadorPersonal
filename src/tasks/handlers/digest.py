"""Handler digest matutino único."""
from __future__ import annotations

from src.telegram.escalation import enviar_digest_matutino


async def handle(bot, doc: dict) -> None:
    telegram_id = int(doc.get("telegram_id") or 0)
    if telegram_id:
        await enviar_digest_matutino(bot, telegram_id)
