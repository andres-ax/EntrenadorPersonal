"""Tracking de hidratacion + calculo de objetivo diario."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from src.db.connection import async_session_factory
from src.db.models import ConsumoAgua, SesionEntrenamiento, Usuario

logger = logging.getLogger(__name__)


async def registrar_agua(telegram_id: int, ml: int) -> int:
    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return 0
        c = ConsumoAgua(usuario_id=user.id, ml=ml)
        session.add(c)
        await session.commit()
        return ml


async def consumo_hoy_ml(telegram_id: int) -> int:
    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return 0
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(user.timezone or "America/Bogota")
        hoy_user = datetime.now(tz).date()
        hoy_inicio_local = datetime.combine(hoy_user, datetime.min.time(), tzinfo=tz)
        # Convertir a datetime naive en el servidor
        hoy_inicio_servidor = hoy_inicio_local.astimezone().replace(tzinfo=None)

        result = await session.execute(
            select(func.sum(ConsumoAgua.ml)).where(
                ConsumoAgua.usuario_id == user.id,
                ConsumoAgua.registrado_en >= hoy_inicio_servidor,
            )
        )
        return int(result.scalar() or 0)


async def objetivo_ml(telegram_id: int) -> int:
    """Objetivo diario = peso_kg * 35ml + 500ml por entreno hoy."""
    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return 2500
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(user.timezone or "America/Bogota")
        hoy_user = datetime.now(tz).date()

        base = int((user.peso_kg or 70) * 35)
        entrenos_q = await session.execute(
            select(func.count(SesionEntrenamiento.id)).where(
                SesionEntrenamiento.usuario_id == user.id,
                SesionEntrenamiento.fecha == hoy_user,
            )
        )
        n_entrenos = int(entrenos_q.scalar() or 0)
        return base + n_entrenos * 500
