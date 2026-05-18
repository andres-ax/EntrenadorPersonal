"""Jobs deporte-aware (PR3 expansion 67 deportes).

5 jobs adicionales al scheduler base que se activan SOLO si el usuario tiene
la categoria correspondiente:

- recordar_sesion_skill: urbano, L-S 10:00 local si streak_skill_hoy=0
- peso_diario_camp: combate, diario 07:00 si fight_date < 8 sem
- recovery_post_sparring: +48h post sesion subtipo=SPARRING intensidad>=7
- taper_alert: -14d antes de fight_date
- weekly_load_endurance: outdoor_endurance, Lun 07:00, TSS + deload alert

Todos respetan: bot_bloqueado, pausado_hasta, quiet_hours_inicio/fin del user
(via el helper _enviar_safe del scheduler base).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Awaitable, Callable

from sqlalchemy import select
from telegram.ext import Application, ContextTypes

from src.db.connection import async_session_factory
from src.db.models import (
    CategoriaDeporte,
    Compromiso,
    PersonalRecord,
    SesionEntrenamiento,
    SubtipoSesion,
    TipoPR,
    Usuario,
)
from src.db.repository import listar_usuarios_activos

logger = logging.getLogger(__name__)


async def _enviar(
    bot, chat_id: int, texto: str, silent: bool = False
) -> None:
    """Helper minimal: importa la implementacion del scheduler base si existe."""
    try:
        from src.telegram.scheduler import _enviar_safe

        await _enviar_safe(bot, chat_id, texto, silent=silent)
    except ImportError:
        try:
            from telegram.constants import ParseMode

            await bot.send_message(
                chat_id=chat_id,
                text=texto,
                parse_mode=ParseMode.HTML,
                disable_notification=silent,
            )
        except Exception:
            logger.warning("No pude enviar a %s", chat_id)


async def _usuarios_por_categoria(categoria: CategoriaDeporte) -> list[Usuario]:
    usuarios = await listar_usuarios_activos()
    return [u for u in usuarios if u.categoria_deporte == categoria]


async def recordar_sesion_skill(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """L-S 10:00: para usuarios urbanos, recuerda sesion si no rodaron hoy.

    Solo dispara si el usuario es URBANO y NO tiene sesion skill registrada hoy.
    """
    hoy = date.today()
    if hoy.weekday() == 6:
        return
    try:
        usuarios = await _usuarios_por_categoria(CategoriaDeporte.URBANO)
    except Exception:
        logger.exception("Error listando usuarios urbanos")
        return

    if not usuarios:
        return

    async with async_session_factory() as session:
        for u in usuarios:
            try:
                hay_sesion = await session.execute(
                    select(SesionEntrenamiento.id).where(
                        SesionEntrenamiento.usuario_id == u.id,
                        SesionEntrenamiento.fecha == hoy,
                        SesionEntrenamiento.subtipo == SubtipoSesion.SKILL,
                    ).limit(1)
                )
                if hay_sesion.scalar_one_or_none() is not None:
                    continue
                deporte = u.deporte_principal or "tu deporte"
                texto = (
                    f"Hey <b>{u.nombre or 'crack'}</b>! Ya rodaste hoy de {deporte}? "
                    "Aun queda tiempo. Aunque sea 30 min en el spot mas cerca. "
                    "Cuando termines, cuentame que aterrizaste."
                )
                await _enviar(ctx.bot, u.telegram_id, texto, silent=False)
            except Exception:
                logger.exception("Error recordar_sesion_skill uid=%s", u.telegram_id)


async def _compromiso_con_fight_date(uid: int) -> tuple[Compromiso, date] | None:
    """Si user tiene compromiso activo con fight_date en el futuro (<= 90d), lo devuelve."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Compromiso).where(
                Compromiso.usuario_id == uid,
                Compromiso.activo == True,  # noqa: E712
            ).order_by(Compromiso.fecha_firma.desc()).limit(1)
        )
        c = result.scalar_one_or_none()
        if c is None or c.deadline is None:
            return None
        diff = (c.deadline - date.today()).days
        if 0 < diff <= 90:
            return (c, c.deadline)
        return None


async def peso_diario_camp(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Diario 07:00: para usuarios COMBATE en camp (<= 56d a pelea), pide peso."""
    try:
        usuarios = await _usuarios_por_categoria(CategoriaDeporte.COMBATE)
    except Exception:
        logger.exception("Error listando usuarios combate")
        return

    for u in usuarios:
        try:
            uid_db = u.id
            info = await _compromiso_con_fight_date(uid_db)
            if info is None:
                continue
            _compromiso, fight_date = info
            diff_dias = (fight_date - date.today()).days
            if diff_dias > 56:
                continue
            texto = (
                f"<b>{u.nombre or 'crack'}</b>, pesaje matutino. Mandame tu peso "
                f"en ayunas. Quedan <b>{diff_dias} dias</b> para tu pelea. "
                "Tracking diario te mantiene safe."
            )
            await _enviar(ctx.bot, u.telegram_id, texto, silent=False)
        except Exception:
            logger.exception("Error peso_diario_camp uid=%s", u.telegram_id)


async def recovery_post_sparring(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Diario 20:00: si user tuvo sparring intensidad>=7 hace ~48h, screening recovery."""
    try:
        usuarios = await _usuarios_por_categoria(CategoriaDeporte.COMBATE)
    except Exception:
        logger.exception("Error listando usuarios combate")
        return

    hace_48h = date.today() - timedelta(days=2)
    async with async_session_factory() as session:
        for u in usuarios:
            try:
                result = await session.execute(
                    select(SesionEntrenamiento).where(
                        SesionEntrenamiento.usuario_id == u.id,
                        SesionEntrenamiento.subtipo == SubtipoSesion.SPARRING,
                        SesionEntrenamiento.fecha == hace_48h,
                        SesionEntrenamiento.intensidad_1_10 >= 7,
                    ).limit(1)
                )
                if result.scalar_one_or_none() is None:
                    continue
                texto = (
                    f"<b>{u.nombre or 'crack'}</b>, hace 2 dias tuviste sparring "
                    "fuerte. Como esta el cuerpo (1-5)? Algun sintoma de cabeza "
                    "(mareo, dolor, dificultad para concentrarte)? Si si, "
                    "respondeme y vemos."
                )
                await _enviar(ctx.bot, u.telegram_id, texto, silent=False)
            except Exception:
                logger.exception("Error recovery_post_sparring uid=%s", u.telegram_id)


async def taper_alert(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Diario 09:00: si user tiene pelea en exactamente 14 dias, avisa entrar a taper."""
    try:
        usuarios = await _usuarios_por_categoria(CategoriaDeporte.COMBATE)
    except Exception:
        logger.exception("Error listando usuarios combate")
        return

    objetivo = date.today() + timedelta(days=14)
    for u in usuarios:
        try:
            info = await _compromiso_con_fight_date(u.id)
            if info is None:
                continue
            _c, fight_date = info
            if fight_date != objetivo:
                continue
            texto = (
                f"<b>{u.nombre or 'crack'}</b>, entras a TAPER. 14 dias para tu pelea.\n\n"
                "Reglas del taper (Mujika 2003, Bosquet 2007):\n"
                "- Reduce volumen S&C <b>50%</b>\n"
                "- Mantener intensidad (no es deload, es tapering)\n"
                "- <b>NO hard sparring</b> esta semana\n"
                "- Drilling + flow + mind work\n\n"
                "Si haces cut, recuerda 0.5-0.7%/sem cronico. NUNCA diureticos ni sauna prolongada."
            )
            await _enviar(ctx.bot, u.telegram_id, texto, silent=False)
        except Exception:
            logger.exception("Error taper_alert uid=%s", u.telegram_id)


async def weekly_load_endurance(ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Lun 07:00: para outdoor_endurance, resumen carga + alerta deload si volumen 4 semanas creciente."""
    try:
        usuarios = await _usuarios_por_categoria(CategoriaDeporte.OUTDOOR_ENDURANCE)
    except Exception:
        logger.exception("Error listando usuarios endurance")
        return

    hace_4_sem = date.today() - timedelta(days=28)
    hace_1_sem = date.today() - timedelta(days=7)
    async with async_session_factory() as session:
        for u in usuarios:
            try:
                result_all = await session.execute(
                    select(SesionEntrenamiento).where(
                        SesionEntrenamiento.usuario_id == u.id,
                        SesionEntrenamiento.fecha >= hace_4_sem,
                    )
                )
                sesiones = list(result_all.scalars().all())
                if not sesiones:
                    continue
                min_4_sem = sum(s.duracion_min or 0 for s in sesiones)
                min_promedio_sem = min_4_sem / 4
                min_ultima_sem = sum(
                    s.duracion_min or 0 for s in sesiones if s.fecha >= hace_1_sem
                )
                alerta_deload = (
                    min_promedio_sem > 0 and min_ultima_sem > 1.5 * min_promedio_sem
                )

                lineas = [
                    f"<b>{u.nombre or 'Crack'}</b>, resumen tu semana endurance:",
                    f"- Tiempo: <b>{min_ultima_sem} min</b>",
                    f"- Sesiones: <b>{sum(1 for s in sesiones if s.fecha >= hace_1_sem)}</b>",
                    f"- Promedio 4 sem: {round(min_promedio_sem)} min/sem",
                ]
                if alerta_deload:
                    lineas.append(
                        "\n<b>Alerta:</b> tu semana fue >150% del promedio. "
                        "Considera deload (40-60% volumen) esta semana para "
                        "evitar overtraining (Meeusen 2013, Mountjoy IOC 2018)."
                    )
                else:
                    lineas.append("\nSemana razonable. Sigue asi.")
                await _enviar(
                    ctx.bot, u.telegram_id, "\n".join(lineas), silent=True
                )
            except Exception:
                logger.exception("Error weekly_load_endurance uid=%s", u.telegram_id)


def registrar_jobs_deportes(app: Application) -> None:
    """Registra los 5 jobs deporte-aware. Llamar desde scheduler.registrar_jobs()."""
    jq = app.job_queue
    if jq is None:
        return

    jq.run_daily(recordar_sesion_skill, time=time(10, 0), name="recordar_sesion_skill")
    jq.run_daily(peso_diario_camp, time=time(7, 0), name="peso_diario_camp")
    jq.run_daily(recovery_post_sparring, time=time(20, 0), name="recovery_post_sparring")
    jq.run_daily(taper_alert, time=time(9, 0), name="taper_alert")
    jq.run_daily(
        weekly_load_endurance, time=time(7, 0), days=(0,), name="weekly_load_endurance"
    )

    logger.info(
        "5 jobs deporte-aware registrados: sesion_skill, peso_diario_camp, "
        "recovery_post_sparring, taper_alert, weekly_load_endurance"
    )
