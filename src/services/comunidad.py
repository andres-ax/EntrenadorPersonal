"""Logica de desafios + kudos para comunidad gamificada."""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import desc, func, select

from src.db.connection import async_session_factory
from src.db.models import (
    Desafio,
    DesafioParticipante,
    Kudos,
    Usuario,
)

logger = logging.getLogger(__name__)


async def listar_desafios_activos() -> list[Desafio]:
    hoy = date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Desafio).where(
                Desafio.fecha_inicio <= hoy, Desafio.fecha_fin >= hoy
            ).order_by(Desafio.fecha_inicio.desc())
        )
        return list(result.scalars().all())


async def inscribir_en_desafio(telegram_id: int, desafio_slug: str) -> bool:
    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return False
        des_q = await session.execute(
            select(Desafio).where(Desafio.slug == desafio_slug)
        )
        des = des_q.scalar_one_or_none()
        if des is None:
            return False
        existing_q = await session.execute(
            select(DesafioParticipante).where(
                DesafioParticipante.desafio_id == des.id,
                DesafioParticipante.usuario_id == user.id,
            )
        )
        if existing_q.scalar_one_or_none() is not None:
            return False
        p = DesafioParticipante(desafio_id=des.id, usuario_id=user.id)
        session.add(p)
        await session.commit()
        return True


async def ranking_desafio(desafio_slug: str, top: int = 10) -> list[dict]:
    async with async_session_factory() as session:
        des_q = await session.execute(
            select(Desafio).where(Desafio.slug == desafio_slug)
        )
        des = des_q.scalar_one_or_none()
        if des is None:
            return []
        result = await session.execute(
            select(DesafioParticipante, Usuario)
            .join(Usuario, Usuario.id == DesafioParticipante.usuario_id)
            .where(DesafioParticipante.desafio_id == des.id)
            .order_by(DesafioParticipante.valor_actual.desc())
            .limit(top)
        )
        rows = result.all()
    return [
        {
            "posicion": i + 1,
            "nombre": u.nombre or f"Atleta{u.id}",
            "valor": p.valor_actual,
        }
        for i, (p, u) in enumerate(rows)
    ]


async def mi_posicion(telegram_id: int) -> list[dict]:
    """Posicion del usuario en cada desafio activo donde participa."""
    hoy = date.today()
    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return []
        result = await session.execute(
            select(DesafioParticipante, Desafio)
            .join(Desafio, Desafio.id == DesafioParticipante.desafio_id)
            .where(
                DesafioParticipante.usuario_id == user.id,
                Desafio.fecha_inicio <= hoy,
                Desafio.fecha_fin >= hoy,
            )
        )
        rows = result.all()
    return [
        {
            "desafio": d.titulo,
            "posicion": p.posicion or 0,
            "valor": p.valor_actual,
        }
        for p, d in rows
    ]


async def dar_kudos(
    origen_telegram_id: int, destino_telegram_id: int, tipo: str = "pr"
) -> bool:
    """Limite: 10/dia por usuario origen."""
    async with async_session_factory() as session:
        origen_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == origen_telegram_id)
        )
        origen = origen_q.scalar_one_or_none()
        destino_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == destino_telegram_id)
        )
        destino = destino_q.scalar_one_or_none()
        if origen is None or destino is None or origen.id == destino.id:
            return False
        hoy = date.today()
        count_q = await session.execute(
            select(func.count(Kudos.id)).where(
                Kudos.usuario_origen == origen.id,
                func.date(Kudos.creado_en) == hoy,
            )
        )
        n_hoy = count_q.scalar() or 0
        if n_hoy >= 10:
            return False
        k = Kudos(
            usuario_origen=origen.id,
            usuario_destino=destino.id,
            tipo=tipo,
        )
        session.add(k)
        await session.commit()
        return True
