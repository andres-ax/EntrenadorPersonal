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
    bot, chat_id: int, texto: str, parse_mode: str | None = ParseMode.HTML
) -> None:
    async with _SEND_SEMAPHORE:
        try:
            await bot.send_message(chat_id=chat_id, text=texto, parse_mode=parse_mode)
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
    await asyncio.gather(*[_enviar_safe(bot, uid, txt) for uid, txt in pares])
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
    """Diario 8am: avisa a quienes llevan 2+ dias sin entrenar."""

    async def _build(u: Usuario) -> str | None:
        dias = await _dias_sin_entrenar(u.id)
        if dias < 2:
            return None
        return (
            f"Hey <b>{u.nombre or 'crack'}</b>! Llevas <b>{dias} dias</b> sin "
            "registrar entrenamiento. Como va todo? Si entrenaste y no lo "
            "registraste, cuentame. Si descansaste, tambien esta bien, el "
            "descanso es progreso."
        )

    try:
        usuarios = await listar_usuarios_activos()
        n = await _broadcast(context.bot, usuarios, _build)
        logger.info("recordatorio_entreno enviado a %s usuarios", n)
    except Exception:
        logger.exception("Error en recordatorio_entreno")


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
        await _broadcast(context.bot, usuarios, _build)
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
        await _broadcast(context.bot, usuarios, _build)
    except Exception:
        logger.exception("Error en checkin_nocturno")


def registrar_jobs(app: Application) -> None:
    """Registra los jobs recurrentes en el JobQueue de la app."""
    jq = app.job_queue
    if jq is None:
        logger.warning("JobQueue no disponible. Instala python-telegram-bot[job-queue]")
        return

    jq.run_daily(
        recordatorio_entreno,
        time=HORA_RECORDATORIO_ENTRENO,
        name="recordatorio_entreno",
    )
    jq.run_daily(
        recordatorio_sueno, time=HORA_RECORDATORIO_SUENO, name="recordatorio_sueno"
    )
    jq.run_daily(
        recordatorio_comida, time=HORA_RECORDATORIO_COMIDA, name="recordatorio_comida"
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

    logger.info(
        "6 jobs de recordatorios registrados: entreno, sueno, comida, checkin, peso, resumen"
    )
