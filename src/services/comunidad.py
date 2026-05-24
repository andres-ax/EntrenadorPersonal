"""Logica de desafios + kudos para comunidad gamificada."""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import desc, func, select

from src.db.connection import async_session_factory
from src.db.models import (
    Desafio,
    DesafioParticipante,
    Kudos,
    Usuario,
)
from src.services.desafios.cohorte import cohorte_key_usuario
from src.services.desafios.generador import asegurar_desafio_cohorte_dia, slug_desafio_dia
from src.timezone_utils import fecha_hoy_usuario

logger = logging.getLogger(__name__)


async def listar_desafios_activos() -> list[Desafio]:
    hoy = date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Desafio).where(
                Desafio.fecha_inicio <= hoy,
                Desafio.fecha_fin >= hoy,
                Desafio.estado == "activo",
            ).order_by(Desafio.fecha_inicio.desc())
        )
        return list(result.scalars().all())


async def activar_desafios(telegram_id: int) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return False
        user.desafios_opt_in = True
        await session.commit()
        return True


async def desactivar_desafios(telegram_id: int) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return False
        user.desafios_opt_in = False
        await session.commit()
        return True


async def usuario_tiene_opt_in(telegram_id: int) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario.desafios_opt_in).where(Usuario.telegram_id == telegram_id)
        )
        val = result.scalar_one_or_none()
        return bool(val)


async def desafio_cohorte_hoy(telegram_id: int) -> Desafio | None:
    hoy = await fecha_hoy_usuario(telegram_id)
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            return None
        cohorte_key = cohorte_key_usuario(user)
        slug = slug_desafio_dia(hoy, cohorte_key)
        des_q = await session.execute(
            select(Desafio).where(
                Desafio.slug == slug,
                Desafio.estado == "activo",
            )
        )
        return des_q.scalar_one_or_none()


async def participacion_usuario(
    telegram_id: int, desafio_id: int
) -> DesafioParticipante | None:
    async with async_session_factory() as session:
        uq = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = uq.scalar_one_or_none()
        if user is None:
            return None
        pq = await session.execute(
            select(DesafioParticipante).where(
                DesafioParticipante.desafio_id == desafio_id,
                DesafioParticipante.usuario_id == user.id,
            )
        )
        return pq.scalar_one_or_none()


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
        if des is None or des.estado != "activo":
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
        await recalcular_ranking(des.id)
        return True


async def inscribir_en_desafio_cohorte(telegram_id: int) -> bool:
    """Opt-in + asegura desafío del día + inscribe."""
    if not await activar_desafios(telegram_id):
        return False
    des = await asegurar_desafio_cohorte_dia(telegram_id)
    if des is None:
        return False
    return await inscribir_en_desafio(telegram_id, des.slug)


async def recalcular_ranking(desafio_id: int) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(DesafioParticipante)
            .where(DesafioParticipante.desafio_id == desafio_id)
            .order_by(desc(DesafioParticipante.valor_actual))
        )
        participantes = list(result.scalars().all())
        for i, p in enumerate(participantes, start=1):
            p.posicion = i
        await session.commit()


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
            "usuario_id": u.id,
            "telegram_id": u.telegram_id,
            "nombre": u.nombre or f"Atleta{u.id}",
            "valor": p.valor_actual,
        }
        for i, (p, u) in enumerate(rows)
    ]


async def mi_posicion(telegram_id: int) -> list[dict]:
    """Posicion del usuario en cada desafio activo donde participa."""
    hoy = await fecha_hoy_usuario(telegram_id)
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
                Desafio.estado == "activo",
            )
        )
        rows = result.all()
    return [
        {
            "desafio": d.titulo,
            "slug": d.slug,
            "posicion": p.posicion or 0,
            "valor": p.valor_actual,
            "meta": d.meta_valor,
            "metrica": d.metrica,
        }
        for p, d in rows
    ]


async def estado_desafio_usuario(telegram_id: int) -> dict | None:
    """Resumen del desafío de cohorte de hoy para el usuario."""
    des = await desafio_cohorte_hoy(telegram_id)
    if des is None:
        des = await asegurar_desafio_cohorte_dia(telegram_id)
    if des is None:
        return None
    part = await participacion_usuario(telegram_id, des.id)
    return {
        "desafio": des,
        "participante": part,
        "inscrito": part is not None,
        "valor": part.valor_actual if part else 0.0,
        "posicion": part.posicion if part else None,
    }


async def contar_desafios_activos_hoy() -> int:
    hoy = date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(Desafio.id)).where(
                Desafio.fecha_inicio <= hoy,
                Desafio.fecha_fin >= hoy,
                Desafio.estado == "activo",
                Desafio.auto_generado == True,  # noqa: E712
            )
        )
        return int(result.scalar() or 0)


async def listar_desafios_por_fecha(fecha: date) -> list[Desafio]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Desafio).where(
                Desafio.fecha_inicio == fecha,
                Desafio.auto_generado == True,  # noqa: E712
            ).order_by(Desafio.cohorte_key)
        )
        return list(result.scalars().all())


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
