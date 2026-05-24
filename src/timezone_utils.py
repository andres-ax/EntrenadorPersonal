"""Utilidades de timezone por usuario (America/Bogota por defecto)."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import Usuario

_TZ_CACHE: dict[int, ZoneInfo] = {}


def zoneinfo_for(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or settings.default_timezone)
    except Exception:
        return ZoneInfo(settings.default_timezone)


async def tz_usuario(telegram_id: int) -> ZoneInfo:
    if telegram_id in _TZ_CACHE:
        return _TZ_CACHE[telegram_id]
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario.timezone).where(Usuario.telegram_id == telegram_id)
        )
        row = result.scalar_one_or_none()
    tz = zoneinfo_for(row)
    _TZ_CACHE[telegram_id] = tz
    return tz


def invalidar_tz_cache(telegram_id: int) -> None:
    _TZ_CACHE.pop(telegram_id, None)


async def ahora_usuario(telegram_id: int) -> datetime:
    return datetime.now(await tz_usuario(telegram_id))


async def fecha_hoy_usuario(telegram_id: int) -> date:
    return (await ahora_usuario(telegram_id)).date()


async def fecha_hoy_usuario_model(usuario: Usuario) -> date:
    return datetime.now(zoneinfo_for(usuario.timezone)).date()


def rango_dia_usuario(
    dia: date, tz_name: str | None
) -> tuple[datetime, datetime]:
    """Inicio y fin del día calendario del usuario en UTC naive (para comparar DB)."""
    tz = zoneinfo_for(tz_name)
    inicio = datetime.combine(dia, datetime.min.time(), tzinfo=tz)
    fin = datetime.combine(dia, datetime.max.time(), tzinfo=tz)
    return (
        inicio.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        fin.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
    )
