"""Migracion one-shot: sesiones Redis legacy uid -> conv:{id}."""
from __future__ import annotations

import logging

from sqlalchemy import select

from src.cache import get_redis
from src.db.connection import async_session_factory
from src.db.models import Usuario
from src.services.conversation_service import (
    asegurar_conversacion_principal,
    session_key_for_conversacion,
)

logger = logging.getLogger(__name__)

_MIGRATION_FLAG = "migration:conv_redis_v1"


async def migrar_sesiones_redis_legacy() -> int:
    """Copia agents:session:{telegram_id}* a agents:session:conv:{id}* por usuario."""
    client = await get_redis()
    if await client.get(_MIGRATION_FLAG):
        return 0

    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario.telegram_id).where(Usuario.telegram_id.isnot(None))
        )
        telegram_ids = [row[0] for row in result.all() if row[0]]

    renombradas = 0
    for tid in telegram_ids:
        try:
            conv = await asegurar_conversacion_principal(tid)
            new_sid = session_key_for_conversacion(conv.id)
            dest_prefix = f"agents:session:{new_sid}"
            has_dest = False
            async for _ in client.scan_iter(match=f"{dest_prefix}*"):
                has_dest = True
                break
            if has_dest:
                continue

            old_prefix = f"agents:session:{tid}"
            async for key in client.scan_iter(match=f"{old_prefix}*"):
                new_key = key.replace(f"agents:session:{tid}", dest_prefix, 1)
                try:
                    await client.rename(key, new_key)
                    renombradas += 1
                except Exception:
                    logger.warning("No pude renombrar %s -> %s", key, new_key, exc_info=True)
        except Exception:
            logger.exception("Error migrando sesion Redis uid=%s", tid)

    await client.setex(_MIGRATION_FLAG, 86400 * 365, "done")
    logger.info("Migracion Redis conversaciones: %s keys renombradas", renombradas)
    return renombradas
