"""Jobs de comunidad: recalcular rankings, premios automaticos."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import func, select

from src.db.connection import async_session_factory
from src.db.models import (
    Desafio,
    DesafioParticipante,
    SesionEntrenamiento,
    Streak,
    TipoStreak,
)

logger = logging.getLogger(__name__)


async def recalcular_rankings(ctx) -> int:
    """Recalcula valor_actual de cada participante en cada desafio activo."""
    hoy = date.today()
    actualizados = 0
    async with async_session_factory() as session:
        desafios_q = await session.execute(
            select(Desafio).where(
                Desafio.fecha_inicio <= hoy, Desafio.fecha_fin >= hoy
            )
        )
        desafios = list(desafios_q.scalars().all())
        for d in desafios:
            parts_q = await session.execute(
                select(DesafioParticipante).where(
                    DesafioParticipante.desafio_id == d.id
                )
            )
            participantes = list(parts_q.scalars().all())
            for p in participantes:
                valor = await _calcular_valor_desafio(
                    session, p.usuario_id, d.tipo, d.fecha_inicio, d.fecha_fin
                )
                p.valor_actual = valor
                actualizados += 1
            participantes.sort(key=lambda x: x.valor_actual, reverse=True)
            for i, p in enumerate(participantes):
                p.posicion = i + 1
        await session.commit()
    logger.info("Rankings recalculados: %s participantes", actualizados)
    return actualizados


async def _calcular_valor_desafio(
    session, usuario_id: int, tipo: str, inicio: date, fin: date
) -> float:
    if tipo == "dias":
        q = select(func.count(func.distinct(SesionEntrenamiento.fecha))).where(
            SesionEntrenamiento.usuario_id == usuario_id,
            SesionEntrenamiento.fecha >= inicio,
            SesionEntrenamiento.fecha <= fin,
        )
        return float((await session.execute(q)).scalar() or 0)
    if tipo == "streak":
        q = select(Streak.dias_actuales).where(
            Streak.usuario_id == usuario_id,
            Streak.tipo_streak == TipoStreak.ENTRENO,
        )
        return float((await session.execute(q)).scalar() or 0)
    if tipo == "volumen":
        q = select(
            func.sum(SesionEntrenamiento.duracion_min)
        ).where(
            SesionEntrenamiento.usuario_id == usuario_id,
            SesionEntrenamiento.fecha >= inicio,
            SesionEntrenamiento.fecha <= fin,
        )
        return float((await session.execute(q)).scalar() or 0)
    return 0.0
