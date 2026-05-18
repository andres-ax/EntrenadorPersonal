"""Publicacion automatica en canal publico @entrenadorax_logros.

PRs anonimizados (o con nombre + ciudad si user opted-in) para social proof
y motivacion comunitaria.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from src.cache import get_redis
from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import EventoBot, PersonalRecord, Usuario

logger = logging.getLogger(__name__)


async def opt_in_canal_logros(telegram_id: int) -> bool:
    """Marca al usuario como opted-in para que sus PRs salgan al canal."""
    client = await get_redis()
    await client.set(f"canal_logros_optin:{telegram_id}", "1", ex=365 * 24 * 3600)
    return True


async def opt_out_canal_logros(telegram_id: int) -> bool:
    client = await get_redis()
    await client.delete(f"canal_logros_optin:{telegram_id}")
    return True


async def esta_opted_in(telegram_id: int) -> bool:
    client = await get_redis()
    val = await client.get(f"canal_logros_optin:{telegram_id}")
    return val == "1"


async def publicar_pr(
    bot, telegram_id: int, pr: PersonalRecord, ciudad: Optional[str] = None
) -> bool:
    """Publica un PR en el canal de logros. Devuelve True si publico."""
    if settings.canal_logros_id is None:
        return False
    if not await esta_opted_in(telegram_id):
        return False
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        u = result.scalar_one_or_none()
    nombre = (u.nombre.split()[0] if u and u.nombre else "Atleta")
    pais = (u.pais if u else "?") if not ciudad else ciudad
    mensaje = (
        f"<b>{nombre}</b> ({pais}) acaba de hacer "
        f"<b>{pr.ejercicio}</b>: {pr.peso_kg}kg x{pr.reps}\n\n"
        f"Tu turno. https://t.me/{getattr(bot, 'username', 'entrenadorax_bot')}"
    )
    try:
        await bot.send_message(
            chat_id=settings.canal_logros_id,
            text=mensaje,
        )
        async with async_session_factory() as session:
            ev = EventoBot(
                usuario_id=(u.id if u else None),
                tipo_evento="pr_publicado_canal",
                payload={"pr_id": pr.id, "ejercicio": pr.ejercicio, "kg": pr.peso_kg},
            )
            session.add(ev)
            await session.commit()
        return True
    except Exception:
        logger.exception("Error publicando PR en canal uid=%s", telegram_id)
        return False
