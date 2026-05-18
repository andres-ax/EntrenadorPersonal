"""Recordatorios proactivos con JobQueue (APScheduler) + rate-limit safe."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, time
from typing import Awaitable, Callable

import telegram.error
from sqlalchemy import func, select
from telegram.constants import ParseMode
from telegram.ext import Application

from src.db.connection import async_session_factory
from src.db.models import (
    Comida,
    MetricaCorporal,
    MetricaSueno,
    SesionEntrenamiento,
    TipoComida,
    Usuario,
)
from src.db.repository import (
    listar_usuarios_activos,
    marcar_bot_bloqueado,
    reporte_semanal,
)

logger = logging.getLogger(__name__)

HORA_RECORDATORIO_ENTRENO = time(hour=8, minute=0)
HORA_RECORDATORIO_SUENO = time(hour=9, minute=0)
HORA_RECORDATORIO_COMIDA = time(hour=14, minute=0)
HORA_CHECKIN_NOCTURNO = time(hour=21, minute=0)
HORA_RESUMEN_DOMINGO = time(hour=20, minute=0)

_SEND_SEMAPHORE = asyncio.Semaphore(20)
_SEND_DELAY_S = 0.04


async def _enviar_safe(
    bot,
    chat_id: int,
    texto: str,
    parse_mode: str | None = ParseMode.HTML,
    silent: bool = False,
) -> None:
    async with _SEND_SEMAPHORE:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=texto,
                parse_mode=parse_mode,
                disable_notification=silent,
            )
            await asyncio.sleep(_SEND_DELAY_S)
        except telegram.error.Forbidden:
            await marcar_bot_bloqueado(chat_id, True)
            logger.info("Bot bloqueado por %s, marcado en DB", chat_id)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            logger.warning("Error enviando a %s: %s", chat_id, e)


async def _broadcast(
    bot,
    usuarios: list[Usuario],
    builder: Callable[[Usuario], Awaitable[str | None]],
    silent: bool = False,
) -> int:
    """Construye un mensaje por usuario y los envia en paralelo (rate-limited)."""
    pares: list[tuple[int, str]] = []
    for u in usuarios:
        try:
            txt = await builder(u)
            if txt:
                pares.append((u.telegram_id, txt))
        except Exception:
            logger.exception("Error construyendo mensaje para %s", u.telegram_id)
    if not pares:
        return 0
    await asyncio.gather(
        *[_enviar_safe(bot, uid, txt, silent=silent) for uid, txt in pares]
    )
    return len(pares)


async def _dias_sin_entrenar(usuario_id: int) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.max(SesionEntrenamiento.fecha)).where(
                SesionEntrenamiento.usuario_id == usuario_id
            )
        )
        ultima_fecha = result.scalar()
        if ultima_fecha is None:
            return 999
        return (date.today() - ultima_fecha).days


async def _dias_sin_pesarse(usuario_id: int) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.max(MetricaCorporal.fecha)).where(
                MetricaCorporal.usuario_id == usuario_id
            )
        )
        ultima_fecha = result.scalar()
        if ultima_fecha is None:
            return 999
        return (date.today() - ultima_fecha).days


async def _registro_sueno_hoy(usuario_id: int) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(MetricaSueno.id)).where(
                MetricaSueno.usuario_id == usuario_id,
                MetricaSueno.fecha == date.today(),
            )
        )
        return (result.scalar() or 0) > 0


async def _registro_comida_hoy(usuario_id: int, tipo_comida: str = "almuerzo") -> bool:
    """Verifica si registro un TIPO especifico de comida hoy (fix del bug previo)."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(Comida.id)).where(
                Comida.usuario_id == usuario_id,
                Comida.fecha == date.today(),
                Comida.tipo == TipoComida(tipo_comida),
            )
        )
        return (result.scalar() or 0) > 0


async def _entreno_hoy(usuario_id: int) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(SesionEntrenamiento.id)).where(
                SesionEntrenamiento.usuario_id == usuario_id,
                SesionEntrenamiento.fecha == date.today(),
            )
        )
        return (result.scalar() or 0) > 0


async def recordatorio_entreno(context) -> None:
    """Diario 8am: dispara el sistema de escalation (entreno/sueno/comida)."""
    from src.telegram.escalation import disparar_escalado_inicial

    try:
        await disparar_escalado_inicial(context)
        logger.info("escalation diaria disparada")
    except Exception:
        logger.exception("Error en disparar_escalado_inicial")


async def recordatorio_peso(context) -> None:
    """Semanal lunes: avisa si llevan 7+ dias sin pesarse."""

    async def _build(u: Usuario) -> str | None:
        dias = await _dias_sin_pesarse(u.id)
        if dias < 7:
            return None
        return (
            f"<b>{u.nombre or 'Crack'}</b>, hace mas de una semana que no "
            "registras tu peso. Pesarte regularmente ayuda a trackear progreso. "
            "Dime tu peso cuando puedas!"
        )

    try:
        usuarios = await listar_usuarios_activos()
        await _broadcast(context.bot, usuarios, _build)
    except Exception:
        logger.exception("Error en recordatorio_peso")


async def resumen_semanal(context) -> None:
    """Domingos 8pm: resumen de la semana."""

    async def _build(u: Usuario) -> str | None:
        reporte = await reporte_semanal(u.telegram_id)
        dias = reporte.get("dias_entrenados", 0)
        volumen = reporte.get("volumen_total_kg", 0)
        prs = reporte.get("nuevos_prs", [])

        lineas = [f"<b>Resumen semanal de {u.nombre or 'tu semana'}:</b>"]
        lineas.append(f"- Dias entrenados: <b>{dias}</b>")
        if volumen > 0:
            lineas.append(f"- Volumen total: <b>{volumen:.0f} kg</b>")
        if prs:
            lineas.append(f"- Nuevos PRs: <b>{len(prs)}</b>")
            for pr in prs[:3]:
                lineas.append(f"  {pr['ejercicio']}: {pr['peso_kg']}kg x{pr['reps']}")
        if dias == 0:
            lineas.append("Semana sin entrenos registrados. La proxima va a ser mejor!")
        else:
            lineas.append("Buen trabajo! Sigue asi.")
        return "\n".join(lineas)

    try:
        usuarios = await listar_usuarios_activos()
        await _broadcast(context.bot, usuarios, _build, silent=True)
    except Exception:
        logger.exception("Error en resumen_semanal")


async def recordatorio_sueno(context) -> None:
    """Diario 9am: pregunta como durmio si no registro sueno."""

    async def _build(u: Usuario) -> str | None:
        if await _registro_sueno_hoy(u.id):
            return None
        return (
            f"Buenos dias <b>{u.nombre or 'crack'}</b>! Como dormiste anoche? "
            "Dime cuantas horas y que tal la calidad (1-5) para registrarlo."
        )

    try:
        usuarios = await listar_usuarios_activos()
        await _broadcast(context.bot, usuarios, _build)
    except Exception:
        logger.exception("Error en recordatorio_sueno")


async def recordatorio_comida(context) -> None:
    """Diario 2pm: pregunta que almorzo si no registro."""

    async def _build(u: Usuario) -> str | None:
        if await _registro_comida_hoy(u.id, "almuerzo"):
            return None
        return (
            f"Hey <b>{u.nombre or 'crack'}</b>! Que almorzaste hoy? "
            "Cuentame para registrar tu nutricion del dia."
        )

    try:
        usuarios = await listar_usuarios_activos()
        await _broadcast(context.bot, usuarios, _build)
    except Exception:
        logger.exception("Error en recordatorio_comida")


async def checkin_nocturno(context) -> None:
    """Diario 9pm: check-in general del dia."""

    async def _build(u: Usuario) -> str | None:
        partes = []
        if not await _entreno_hoy(u.id):
            partes.append("no registraste entreno hoy")
        if not await _registro_comida_hoy(u.id, "cena"):
            partes.append("tampoco cena")

        if partes:
            faltante = " y ".join(partes)
            return (
                f"Buenas noches <b>{u.nombre or 'crack'}</b>! Vi que <i>{faltante}</i>. "
                "Si hiciste algo y no lo registraste, cuentame rapido antes de dormir. "
                "Si fue dia de descanso, descansa bien!"
            )
        return (
            f"Gran dia <b>{u.nombre or 'crack'}</b>! Registraste entreno y comida hoy. "
            "Descansa bien esta noche, manana seguimos!"
        )

    try:
        usuarios = await listar_usuarios_activos()
        await _broadcast(context.bot, usuarios, _build, silent=True)
    except Exception:
        logger.exception("Error en checkin_nocturno")


async def recordatorio_hidratacion(context) -> None:
    """Cada 2h en horas activas: avisa si va atras del objetivo."""
    from src.services.hidratacion import consumo_hoy_ml, objetivo_ml

    async def _build(u: Usuario) -> str | None:
        consumido = await consumo_hoy_ml(u.telegram_id)
        objetivo = await objetivo_ml(u.telegram_id)
        if objetivo <= 0:
            return None
        pct = consumido / objetivo
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo as _ZI

        ahora = _dt.now(_ZI(u.timezone or "America/Bogota"))
        if ahora.hour < 8 or ahora.hour >= 21:
            return None
        horas_dia = max(1, ahora.hour - 7)
        pct_esperado = horas_dia / 13
        if pct >= pct_esperado * 0.85:
            return None
        return (
            f"<b>{u.nombre or 'Crack'}</b>, vas en {consumido}ml de "
            f"{objetivo}ml. Tomate <b>500ml</b> de agua."
        )

    try:
        usuarios = await listar_usuarios_activos()
        await _broadcast(context.bot, usuarios, _build, silent=True)
    except Exception:
        logger.exception("Error en recordatorio_hidratacion")


async def reconsent_militar_mensual(context) -> None:
    """Dia 1 de cada mes: pide reconfirmacion del modo militar a quienes lo tienen."""
    from src.db.models import TonoCoach as _Tono

    async def _build(u: Usuario) -> str | None:
        if not u.tono or u.tono != _Tono.MILITAR:
            return None
        return (
            "<b>Reconsent mensual modo militar</b>\n\n"
            "Llevas un mes en modo militar. Como te sentaste? "
            "Responde <b>sigo</b> para mantener, <b>suavizar</b> para bajar a "
            "firme, o usa /pausa N para pausar N dias. "
            "Si no respondes en 7 dias, bajo automaticamente a firme."
        )

    try:
        usuarios = await listar_usuarios_activos()
        await _broadcast(context.bot, usuarios, _build, silent=False)
    except Exception:
        logger.exception("Error en reconsent_militar_mensual")


def registrar_jobs(app: Application) -> None:
    """Registra los jobs recurrentes en el JobQueue de la app."""
    jq = app.job_queue
    if jq is None:
        logger.warning("JobQueue no disponible. Instala python-telegram-bot[job-queue]")
        return

    from src.telegram.quiz import quiz_educativo_semanal, quiz_nocturno

    jq.run_daily(
        recordatorio_entreno,
        time=HORA_RECORDATORIO_ENTRENO,
        name="escalation_diaria",
    )
    jq.run_daily(quiz_nocturno, time=time(21, 30), name="quiz_nocturno")
    jq.run_daily(
        quiz_educativo_semanal,
        time=time(10, 0),
        days=(5,),
        name="quiz_educativo_sabado",
    )
    jq.run_daily(
        checkin_nocturno, time=HORA_CHECKIN_NOCTURNO, name="checkin_nocturno"
    )
    jq.run_daily(
        recordatorio_peso,
        time=HORA_RECORDATORIO_ENTRENO,
        days=(0,),
        name="recordatorio_peso",
    )
    jq.run_daily(
        resumen_semanal,
        time=HORA_RESUMEN_DOMINGO,
        days=(6,),
        name="resumen_semanal",
    )
    jq.run_repeating(
        recordatorio_hidratacion,
        interval=2 * 3600,
        first=time(10, 0),
        name="recordatorio_hidratacion",
    )
    jq.run_monthly(
        reconsent_militar_mensual,
        when=time(10, 0),
        day=1,
        name="reconsent_militar",
    )

    logger.info(
        "8 jobs registrados: escalation, quiz_nocturno, quiz_sabado, checkin, "
        "peso_lunes, resumen_domingo, hidratacion_2h, reconsent_militar"
    )
