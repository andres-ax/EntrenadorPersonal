"""Generación de desafíos diarios por cohorte."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import func, select

from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import Desafio, SesionEntrenamiento, Streak, TipoStreak, Usuario
from src.db.repository import obtener_o_crear_streak
from src.services.desafios.cohorte import cohorte_key_usuario, cohorte_label
from src.services.desafios.plantillas import DEFAULT_PREMIO, calcular_meta, elegir_plantilla

logger = logging.getLogger(__name__)


def slug_desafio_dia(fecha: date, cohorte_key: str) -> str:
    safe = cohorte_key.replace("|", "-")[:40]
    return f"{fecha.isoformat()}-{safe}"


async def _sesiones_ultimos_7(usuario_id: int, hasta: date) -> int:
    desde = hasta - timedelta(days=7)
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(SesionEntrenamiento.id)).where(
                SesionEntrenamiento.usuario_id == usuario_id,
                SesionEntrenamiento.fecha >= desde,
                SesionEntrenamiento.fecha <= hasta,
            )
        )
        return int(result.scalar() or 0)


async def _crear_o_actualizar_desafio(
    fecha: date,
    cohorte_key: str,
    *,
    streak_entreno: int = 0,
    sesiones_ultimos_7: int = 0,
) -> Desafio:
    slug = slug_desafio_dia(fecha, cohorte_key)
    parts = cohorte_key.split("|")
    nivel = parts[1] if len(parts) > 1 else "principiante"
    plantilla = elegir_plantilla(cohorte_key, fecha)
    meta = calcular_meta(
        plantilla,
        nivel,
        streak_entreno=streak_entreno,
        sesiones_ultimos_7=sesiones_ultimos_7,
    )
    label = cohorte_label(cohorte_key)
    titulo = f"{plantilla.titulo} — {label}"
    descripcion = (
        f"{plantilla.descripcion}\n\n"
        f"Meta del día: <b>{meta}</b> ({plantilla.metrica.replace('_', ' ')})"
    )
    reglas = {
        "plantilla": plantilla.metrica,
        "cohorte_key": cohorte_key,
        "nivel": nivel,
    }

    async with async_session_factory() as session:
        existing = await session.execute(select(Desafio).where(Desafio.slug == slug))
        des = existing.scalar_one_or_none()
        if des is not None:
            return des
        des = Desafio(
            slug=slug,
            titulo=titulo,
            descripcion=descripcion,
            fecha_inicio=fecha,
            fecha_fin=fecha,
            tipo="cohorte_dia",
            duracion="dia",
            metrica=plantilla.metrica,
            meta_valor=meta,
            cohorte_key=cohorte_key,
            reglas_json=reglas,
            auto_generado=True,
            estado="activo",
            premio_json=DEFAULT_PREMIO,
        )
        session.add(des)
        await session.commit()
        await session.refresh(des)
        return des


async def generar_desafios_del_dia(fecha: date | None = None) -> list[Desafio]:
    """Crea un desafío por cohorte con usuarios opt-in (sin auto-inscribir)."""
    hoy = fecha or date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(
                Usuario.desafios_opt_in == True,  # noqa: E712
                Usuario.onboarding_completo == True,  # noqa: E712
                Usuario.bot_bloqueado == False,  # noqa: E712
            )
        )
        usuarios = list(result.scalars().all())

    cohortes: dict[str, list[Usuario]] = {}
    for u in usuarios:
        key = cohorte_key_usuario(u)
        cohortes.setdefault(key, []).append(u)

    creados: list[Desafio] = []
    min_part = settings.desafios_min_participantes_cohorte
    for cohorte_key, miembros in cohortes.items():
        if len(miembros) < min_part:
            continue
        rep = miembros[0]
        try:
            streak = await obtener_o_crear_streak(rep.telegram_id, "entreno")
            streak_dias = streak.dias_actuales or 0
        except Exception:
            streak_dias = 0
        sesiones_7 = await _sesiones_ultimos_7(rep.id, hoy)
        try:
            des = await _crear_o_actualizar_desafio(
                hoy,
                cohorte_key,
                streak_entreno=streak_dias,
                sesiones_ultimos_7=sesiones_7,
            )
            creados.append(des)
        except Exception:
            logger.exception("Error creando desafio cohorte=%s", cohorte_key)
    logger.info("Desafios del dia %s: %d cohortes", hoy.isoformat(), len(creados))
    return creados


async def asegurar_desafio_cohorte_dia(telegram_id: int, fecha: date | None = None) -> Desafio | None:
    """Crea desafío de cohorte del día si hay opt-in suficiente (on-demand al activar)."""
    hoy = fecha or date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user is None or not user.desafios_opt_in:
            return None
        cohorte_key = cohorte_key_usuario(user)

    async with async_session_factory() as session:
        all_opt = await session.execute(
            select(Usuario).where(
                Usuario.desafios_opt_in == True,  # noqa: E712
                Usuario.onboarding_completo == True,  # noqa: E712
            )
        )
        miembros_cohorte = [
            u for u in all_opt.scalars().all() if cohorte_key_usuario(u) == cohorte_key
        ]
    if len(miembros_cohorte) < settings.desafios_min_participantes_cohorte:
        return None

    slug = slug_desafio_dia(hoy, cohorte_key)
    async with async_session_factory() as session:
        existing = await session.execute(select(Desafio).where(Desafio.slug == slug))
        found = existing.scalar_one_or_none()
        if found is not None:
            return found

    streak_dias = 0
    sesiones_7 = 0
    async with async_session_factory() as session:
        uq = await session.execute(select(Usuario).where(Usuario.telegram_id == telegram_id))
        u = uq.scalar_one_or_none()
        if u:
            sesiones_7 = await _sesiones_ultimos_7(u.id, hoy)
    try:
        streak = await obtener_o_crear_streak(telegram_id, "entreno")
        streak_dias = streak.dias_actuales or 0
    except Exception:
        pass

    return await _crear_o_actualizar_desafio(
        hoy,
        cohorte_key,
        streak_entreno=streak_dias,
        sesiones_ultimos_7=sesiones_7,
    )
