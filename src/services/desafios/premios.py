"""Premios al cerrar desafíos diarios."""
from __future__ import annotations

import logging

from sqlalchemy import select

from src.cache import get_redis
from src.db.connection import async_session_factory
from src.db.models import Desafio, DesafioParticipante
from src.db.repository import log_evento, obtener_o_crear_streak
from src.services.comunidad import ranking_desafio

logger = logging.getLogger(__name__)

_PREMIO_MSG_TOP1 = (
    "<b>¡Ganaste el desafío del día!</b> 🏆\n"
    "Premio: +1 freeze de racha.\n"
    "Sigue así mañana con /desafios"
)
_PREMIO_MSG_TOP3 = (
    "<b>¡Top 3 en el desafío de hoy!</b> 🥉\n"
    "Gran trabajo. Mañana hay otro reto en /desafios"
)


async def _premio_ya_otorgado(desafio_id: int, usuario_id: int) -> bool:
    client = await get_redis()
    key = f"premio:{desafio_id}:{usuario_id}"
    if await client.get(key):
        return True
    await client.set(key, "1", ex=60 * 60 * 48)
    return False


async def otorgar_freeze(telegram_id: int) -> None:
    streak = await obtener_o_crear_streak(telegram_id, "entreno")
    async with async_session_factory() as session:
        result = await session.execute(
            select(Streak).where(Streak.id == streak.id)
        )
        s = result.scalar_one_or_none()
        if s is None:
            return
        s.freezes_disponibles = (s.freezes_disponibles or 0) + 1
        await session.commit()


async def cerrar_desafio_y_premiar(desafio_id: int) -> dict:
    """Cierra desafío, asigna premios top 3. Devuelve resumen."""
    resumen: dict = {"desafio_id": desafio_id, "premios": []}

    async with async_session_factory() as session:
        des_q = await session.execute(select(Desafio).where(Desafio.id == desafio_id))
        des = des_q.scalar_one_or_none()
        if des is None or des.estado == "cerrado":
            return resumen
        des.estado = "cerrado"
        await session.commit()

    ranking = await ranking_desafio(des.slug, top=3)
    if not ranking:
        return resumen

    async with async_session_factory() as session:
        for entry in ranking:
            pos = entry["posicion"]
            user_id = entry["usuario_id"]
            telegram_id = entry["telegram_id"]
            if await _premio_ya_otorgado(desafio_id, user_id):
                continue

            pq = await session.execute(
                select(DesafioParticipante).where(
                    DesafioParticipante.desafio_id == desafio_id,
                    DesafioParticipante.usuario_id == user_id,
                )
            )
            part = pq.scalar_one_or_none()
            if part is None:
                continue

            premio = None
            msg = None
            if pos == 1:
                premio = "freeze"
                msg = _PREMIO_MSG_TOP1
                await otorgar_freeze(telegram_id)
            elif pos <= 3:
                premio = "badge"
                msg = _PREMIO_MSG_TOP3

            if premio:
                part.premio_otorgado = premio
                await session.commit()
                await log_evento(
                    telegram_id,
                    "desafio_premio",
                    {"desafio_id": desafio_id, "posicion": pos, "premio": premio},
                )
                resumen["premios"].append(
                    {
                        "telegram_id": telegram_id,
                        "posicion": pos,
                        "premio": premio,
                        "mensaje": msg,
                    }
                )

    return resumen
