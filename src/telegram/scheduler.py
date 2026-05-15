"""Sistema de recordatorios proactivos usando python-telegram-bot JobQueue (APScheduler)."""
import logging
from datetime import date, time, timedelta

from telegram.ext import Application

import json

from sqlalchemy import func, select

from src.db.connection import async_session_factory
from src.db.models import Comida, MetricaCorporal, MetricaSueno, SesionEntrenamiento, Usuario
from src.db.repository import reporte_semanal

logger = logging.getLogger(__name__)

HORA_RECORDATORIO_ENTRENO = time(hour=8, minute=0)
HORA_RECORDATORIO_SUENO = time(hour=9, minute=0)
HORA_RECORDATORIO_COMIDA = time(hour=14, minute=0)
HORA_CHECKIN_NOCTURNO = time(hour=21, minute=0)
HORA_RESUMEN_DOMINGO = time(hour=20, minute=0)


async def _obtener_usuarios_activos() -> list[Usuario]:
    """Devuelve todos los usuarios con onboarding completo."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.onboarding_completo == True)  # noqa: E712
        )
        return list(result.scalars().all())


async def _dias_sin_entrenar(usuario_id: int) -> int:
    """Devuelve cuantos dias han pasado desde el ultimo entrenamiento."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.max(SesionEntrenamiento.fecha))
            .where(SesionEntrenamiento.usuario_id == usuario_id)
        )
        ultima_fecha = result.scalar()
        if ultima_fecha is None:
            return 999
        return (date.today() - ultima_fecha).days


async def _dias_sin_pesarse(usuario_id: int) -> int:
    """Devuelve cuantos dias han pasado desde la ultima medicion corporal."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.max(MetricaCorporal.fecha))
            .where(MetricaCorporal.usuario_id == usuario_id)
        )
        ultima_fecha = result.scalar()
        if ultima_fecha is None:
            return 999
        return (date.today() - ultima_fecha).days


async def _registro_sueno_hoy(usuario_id: int) -> bool:
    """Verifica si el usuario ya registro sueno hoy."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(MetricaSueno.id)).where(
                MetricaSueno.usuario_id == usuario_id,
                MetricaSueno.fecha == date.today(),
            )
        )
        return (result.scalar() or 0) > 0


async def _registro_comida_hoy(usuario_id: int, tipo_comida: str = "almuerzo") -> bool:
    """Verifica si el usuario ya registro una comida especifica hoy."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(Comida.id)).where(
                Comida.usuario_id == usuario_id,
                Comida.fecha == date.today(),
            )
        )
        return (result.scalar() or 0) > 0


async def _entreno_hoy(usuario_id: int) -> bool:
    """Verifica si el usuario registro entrenamiento hoy."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(SesionEntrenamiento.id)).where(
                SesionEntrenamiento.usuario_id == usuario_id,
                SesionEntrenamiento.fecha == date.today(),
            )
        )
        return (result.scalar() or 0) > 0


async def recordatorio_entreno(context):
    """Se ejecuta diariamente a las 8am. Avisa a quienes llevan 2+ dias sin entrenar."""
    bot = context.bot
    try:
        usuarios = await _obtener_usuarios_activos()
        for u in usuarios:
            dias = await _dias_sin_entrenar(u.id)
            if dias >= 2:
                texto = (
                    f"Hey {u.nombre or 'crack'}! Llevas {dias} dias sin registrar "
                    "entrenamiento. Como va todo? Si entrenaste y no lo registraste, "
                    "cuentame. Si descansaste, tambien esta bien, el descanso es progreso."
                )
                try:
                    await bot.send_message(chat_id=u.telegram_id, text=texto)
                except Exception as e:
                    logger.warning("No pude enviar recordatorio a %s: %s", u.telegram_id, e)
    except Exception as e:
        logger.exception("Error en recordatorio_entreno: %s", e)


async def recordatorio_peso(context):
    """Se ejecuta semanalmente. Avisa si llevan 7+ dias sin registrar peso."""
    bot = context.bot
    try:
        usuarios = await _obtener_usuarios_activos()
        for u in usuarios:
            dias = await _dias_sin_pesarse(u.id)
            if dias >= 7:
                texto = (
                    f"{u.nombre or 'Crack'}, hace mas de una semana que no registras tu peso. "
                    "Pesarte regularmente ayuda a trackear progreso. "
                    "Dime tu peso cuando puedas!"
                )
                try:
                    await bot.send_message(chat_id=u.telegram_id, text=texto)
                except Exception as e:
                    logger.warning("No pude enviar recordatorio peso a %s: %s", u.telegram_id, e)
    except Exception as e:
        logger.exception("Error en recordatorio_peso: %s", e)


async def resumen_semanal(context):
    """Se ejecuta los domingos. Envia resumen de la semana."""
    bot = context.bot
    try:
        usuarios = await _obtener_usuarios_activos()
        for u in usuarios:
            reporte = await reporte_semanal(u.telegram_id)
            dias = reporte.get("dias_entrenados", 0)
            volumen = reporte.get("volumen_total_kg", 0)
            prs = reporte.get("nuevos_prs", [])

            lineas = [f"Resumen semanal de {u.nombre or 'tu semana'}:"]
            lineas.append(f"- Dias entrenados: {dias}")
            if volumen > 0:
                lineas.append(f"- Volumen total: {volumen:.0f} kg")
            if prs:
                lineas.append(f"- Nuevos PRs: {len(prs)}")
                for pr in prs[:3]:
                    lineas.append(f"  {pr['ejercicio']}: {pr['peso_kg']}kg x{pr['reps']}")
            if dias == 0:
                lineas.append("Semana sin entrenos registrados. La proxima va a ser mejor!")
            else:
                lineas.append("Buen trabajo! Sigue asi.")

            try:
                await bot.send_message(chat_id=u.telegram_id, text="\n".join(lineas))
            except Exception as e:
                logger.warning("No pude enviar resumen a %s: %s", u.telegram_id, e)
    except Exception as e:
        logger.exception("Error en resumen_semanal: %s", e)


async def recordatorio_sueno(context):
    """Se ejecuta diariamente a las 9am. Pregunta como durmio si no registro sueno."""
    bot = context.bot
    try:
        usuarios = await _obtener_usuarios_activos()
        for u in usuarios:
            if not await _registro_sueno_hoy(u.id):
                texto = (
                    f"Buenos dias {u.nombre or 'crack'}! Como dormiste anoche? "
                    "Dime cuantas horas y que tal la calidad (1-5) para registrarlo."
                )
                try:
                    await bot.send_message(chat_id=u.telegram_id, text=texto)
                except Exception as e:
                    logger.warning("No pude enviar recordatorio sueno a %s: %s", u.telegram_id, e)
    except Exception as e:
        logger.exception("Error en recordatorio_sueno: %s", e)


async def recordatorio_comida(context):
    """Se ejecuta diariamente a las 2pm. Pregunta que almorzaron si no registraron comida."""
    bot = context.bot
    try:
        usuarios = await _obtener_usuarios_activos()
        for u in usuarios:
            if not await _registro_comida_hoy(u.id):
                texto = (
                    f"Hey {u.nombre or 'crack'}! Que almorzaste hoy? "
                    "Cuentame para registrar tu nutricion del dia."
                )
                try:
                    await bot.send_message(chat_id=u.telegram_id, text=texto)
                except Exception as e:
                    logger.warning("No pude enviar recordatorio comida a %s: %s", u.telegram_id, e)
    except Exception as e:
        logger.exception("Error en recordatorio_comida: %s", e)


async def checkin_nocturno(context):
    """Se ejecuta diariamente a las 9pm. Hace check-in general del dia."""
    bot = context.bot
    try:
        usuarios = await _obtener_usuarios_activos()
        for u in usuarios:
            partes = []
            if not await _entreno_hoy(u.id):
                partes.append("no registraste entreno hoy")
            if not await _registro_comida_hoy(u.id):
                partes.append("tampoco comida")

            if partes:
                faltante = " y ".join(partes)
                texto = (
                    f"Buenas noches {u.nombre or 'crack'}! Vi que {faltante}. "
                    "Si hiciste algo y no lo registraste, cuentame rapido antes de dormir. "
                    "Si fue dia de descanso, descansa bien!"
                )
            else:
                texto = (
                    f"Gran dia {u.nombre or 'crack'}! Registraste entreno y comida hoy. "
                    "Descansa bien esta noche, manana seguimos!"
                )
            try:
                await bot.send_message(chat_id=u.telegram_id, text=texto)
            except Exception as e:
                logger.warning("No pude enviar checkin a %s: %s", u.telegram_id, e)
    except Exception as e:
        logger.exception("Error en checkin_nocturno: %s", e)


def registrar_jobs(app: Application):
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
        recordatorio_sueno,
        time=HORA_RECORDATORIO_SUENO,
        name="recordatorio_sueno",
    )

    jq.run_daily(
        recordatorio_comida,
        time=HORA_RECORDATORIO_COMIDA,
        name="recordatorio_comida",
    )

    jq.run_daily(
        checkin_nocturno,
        time=HORA_CHECKIN_NOCTURNO,
        name="checkin_nocturno",
    )

    jq.run_daily(
        recordatorio_peso,
        time=HORA_RECORDATORIO_ENTRENO,
        days=(0,),  # Solo lunes
        name="recordatorio_peso",
    )

    jq.run_daily(
        resumen_semanal,
        time=HORA_RESUMEN_DOMINGO,
        days=(6,),  # Solo domingos
        name="resumen_semanal",
    )

    logger.info("6 jobs de recordatorios registrados: entreno, sueno, comida, checkin, peso, resumen")
