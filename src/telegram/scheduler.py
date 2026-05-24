"""Recordatorios proactivos con JobQueue (APScheduler) + rate-limit safe."""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

import telegram.error
from sqlalchemy import func, select
from telegram.constants import ParseMode
from telegram.ext import Application

from src.db.connection import async_session_factory
from src.db.models import (
    Comida,
    MetricaCorporal,
    MetricaSueno,
    Recordatorio,
    SesionEntrenamiento,
    TipoComida,
    Usuario,
)
from src.db.repository import (
    listar_recordatorios_activos_global,
    listar_usuarios_activos,
    marcar_bot_bloqueado,
    marcar_recordatorio_enviado,
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


async def _dias_sin_entrenar(usuario_id: int, u: Usuario | None = None) -> int:
    hoy = fecha_hoy_usuario_model(u) if u else date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.max(SesionEntrenamiento.fecha)).where(
                SesionEntrenamiento.usuario_id == usuario_id
            )
        )
        ultima_fecha = result.scalar()
        if ultima_fecha is None:
            return 999
        return (hoy - ultima_fecha).days


async def _dias_sin_pesarse(usuario_id: int, u: Usuario | None = None) -> int:
    hoy = fecha_hoy_usuario_model(u) if u else date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.max(MetricaCorporal.fecha)).where(
                MetricaCorporal.usuario_id == usuario_id
            )
        )
        ultima_fecha = result.scalar()
        if ultima_fecha is None:
            return 999
        return (hoy - ultima_fecha).days


async def _registro_sueno_hoy(usuario_id: int, u: Usuario | None = None) -> bool:
    hoy = fecha_hoy_usuario_model(u) if u else date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(MetricaSueno.id)).where(
                MetricaSueno.usuario_id == usuario_id,
                MetricaSueno.fecha == hoy,
            )
        )
        return (result.scalar() or 0) > 0


async def _registro_comida_hoy(
    usuario_id: int, tipo_comida: str = "almuerzo", u: Usuario | None = None
) -> bool:
    hoy = fecha_hoy_usuario_model(u) if u else date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(Comida.id)).where(
                Comida.usuario_id == usuario_id,
                Comida.fecha == hoy,
                Comida.tipo == TipoComida(tipo_comida),
            )
        )
        return (result.scalar() or 0) > 0


async def _entreno_hoy(usuario_id: int, u: Usuario | None = None) -> bool:
    hoy = fecha_hoy_usuario_model(u) if u else date.today()
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(SesionEntrenamiento.id)).where(
                SesionEntrenamiento.usuario_id == usuario_id,
                SesionEntrenamiento.fecha == hoy,
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
        dias = await _dias_sin_pesarse(u.id, u)
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
        if await _registro_sueno_hoy(u.id, u):
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
        if await _registro_comida_hoy(u.id, "almuerzo", u):
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
        if not await _entreno_hoy(u.id, u):
            partes.append("no registraste entreno hoy")
        if not await _registro_comida_hoy(u.id, "cena", u):
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


async def enviar_recordatorio_hidratacion_usuario(bot, telegram_id: int) -> None:
    """Envia recordatorio de agua a un usuario si aplica (cap + dedup + objetivo)."""
    from src.services.hidratacion import consumo_hoy_ml, objetivo_ml
    from src.services.proactive_limit import (
        hidratacion_enviada_reciente,
        marcar_hidratacion_enviada,
        puede_enviar_proactivo,
        registrar_envio_proactivo,
    )
    from src.db.repository import obtener_usuario

    u = await obtener_usuario(telegram_id)
    if u is None:
        return
    if not await puede_enviar_proactivo(telegram_id):
        return
    if await hidratacion_enviada_reciente(telegram_id):
        return
    consumido = await consumo_hoy_ml(telegram_id)
    objetivo = await objetivo_ml(telegram_id)
    if objetivo <= 0 or consumido >= objetivo * 0.85:
        return
    ahora = datetime.now(ZoneInfo(u.timezone or "America/Bogota"))
    if ahora.hour < 8 or ahora.hour >= 21:
        return
    horas_dia = max(1, ahora.hour - 7)
    pct = consumido / objetivo
    pct_esperado = horas_dia / 13
    if pct >= pct_esperado * 0.85:
        return
    texto = (
        f"<b>{u.nombre or 'Crack'}</b>, vas en {consumido}ml de "
        f"{objetivo}ml. Tomate <b>500ml</b> de agua."
    )
    await _enviar_safe(bot, telegram_id, texto, silent=True)
    await registrar_envio_proactivo(telegram_id)
    await marcar_hidratacion_enviada(telegram_id)


async def recordatorio_hidratacion(context) -> None:
    """Cada 2h: programa tareas Redis o envia inline segun flag."""
    if settings.use_redis_task_queue:
        try:
            usuarios = await listar_usuarios_activos()
            from src.tasks.scheduling import schedule_hidratacion

            for u in usuarios:
                await schedule_hidratacion(u.telegram_id, offset_minutes=1)
        except Exception:
            logger.exception("Error programando hidratacion Redis")
        return

    try:
        usuarios = await listar_usuarios_activos()
        for u in usuarios:
            await enviar_recordatorio_hidratacion_usuario(context.bot, u.telegram_id)
    except Exception:
        logger.exception("Error en recordatorio_hidratacion")


async def dispatch_tick(context) -> None:
    """Tick cada 30s: dispatcher Redis."""
    if not settings.use_redis_task_queue:
        return
    try:
        from src.tasks.dispatcher import dispatch_due_tasks

        n = await dispatch_due_tasks(context.bot)
        if n:
            logger.debug("Dispatcher procesó %d tareas", n)
    except Exception:
        logger.exception("Error en dispatch_tick")


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


async def enviar_recordatorio_personalizado(context) -> None:
    """Callback de JobQueue para un recordatorio del usuario.

    `context.job.data` trae {'recordatorio_id': int, 'telegram_id': int, 'mensaje': str}.
    Marca `ultimo_envio` y, si es one-shot, lo desactiva (ver repository).
    """
    data = (context.job.data or {}) if context.job else {}
    chat_id = data.get("telegram_id")
    mensaje = data.get("mensaje") or ""
    rid = data.get("recordatorio_id")
    if not chat_id or not mensaje:
        logger.warning("Recordatorio sin chat_id/mensaje data=%s", data)
        return
    try:
        await _enviar_safe(context.bot, int(chat_id), f"<b>Recordatorio:</b> {mensaje}")
        if rid is not None:
            try:
                await marcar_recordatorio_enviado(int(rid))
            except Exception:
                logger.exception("Error marcando recordatorio %s enviado", rid)
    except Exception:
        logger.exception("Error enviando recordatorio_personalizado id=%s", rid)


def _job_names_para(recordatorio_id: int) -> str:
    return f"recordatorio_{recordatorio_id}"


def _normalizar_dias(raw: str) -> tuple[int, ...]:
    """'0,1,4' -> (0,1,4). PTB JobQueue.run_daily acepta tuple de ints 0-6."""
    if not raw:
        return ()
    out: list[int] = []
    for p in raw.split(","):
        p = p.strip()
        if not p.isdigit():
            continue
        n = int(p)
        if 0 <= n <= 6 and n not in out:
            out.append(n)
    return tuple(out)


def programar_recordatorio_en_jobqueue(app: Application, rec: Recordatorio) -> int:
    """Programa un Recordatorio en el JobQueue de la app.

    Devuelve la cantidad de jobs registrados (1 para one-shot/recurrente).
    Para evitar duplicados cuando se reprograma, cancela jobs previos con
    el mismo `name`.
    """
    jq = app.job_queue
    if jq is None:
        logger.warning("JobQueue no disponible; no programo recordatorio %s", rec.id)
        return 0

    name = _job_names_para(rec.id)
    cancelar_recordatorio_jobs(app, rec.id)

    tz = ZoneInfo(rec.tz or "America/Bogota")
    data = {
        "recordatorio_id": rec.id,
        "telegram_id": rec.telegram_id,
        "mensaje": rec.mensaje,
    }

    if rec.dias_semana:
        dias = _normalizar_dias(rec.dias_semana)
        if not dias:
            logger.warning("Recordatorio %s sin dias validos: %r", rec.id, rec.dias_semana)
            return 0
        hora_tz = rec.hora.replace(tzinfo=tz)
        jq.run_daily(
            enviar_recordatorio_personalizado,
            time=hora_tz,
            days=dias,
            name=name,
            data=data,
        )
        logger.info(
            "Recordatorio %s programado recurrente hora=%s dias=%s tz=%s",
            rec.id,
            rec.hora.strftime("%H:%M"),
            dias,
            rec.tz,
        )
        return 1

    fecha = rec.fecha_unica or (datetime.now(tz).date() + timedelta(days=1))
    when_local = datetime.combine(fecha, rec.hora, tzinfo=tz)
    ahora_local = datetime.now(tz)
    if when_local <= ahora_local:
        logger.info(
            "Recordatorio %s one-shot ya paso (%s <= %s), no programo",
            rec.id, when_local, ahora_local,
        )
        return 0

    jq.run_once(
        enviar_recordatorio_personalizado,
        when=when_local,
        name=name,
        data=data,
    )
    logger.info(
        "Recordatorio %s programado one-shot when=%s tz=%s",
        rec.id,
        when_local.isoformat(),
        rec.tz,
    )
    return 1


def cancelar_recordatorio_jobs(app: Application, recordatorio_id: int) -> int:
    """Cancela todos los jobs del JobQueue asociados a `recordatorio_id`."""
    jq = app.job_queue
    if jq is None:
        return 0
    name = _job_names_para(recordatorio_id)
    jobs = jq.get_jobs_by_name(name)
    for job in jobs:
        try:
            job.schedule_removal()
        except Exception:
            logger.exception("Error removiendo job %s", name)
    return len(jobs)


async def _cargar_recordatorios_db(app: Application) -> int:
    """Lee recordatorios activos y los registra en Redis o JobQueue."""
    if settings.use_redis_task_queue:
        from src.tasks.rehydrate import rehydrate_tasks_from_db

        return await rehydrate_tasks_from_db()
    try:
        recordatorios = await listar_recordatorios_activos_global()
    except Exception:
        logger.exception("Error cargando recordatorios activos de DB")
        return 0
    total = 0
    for rec in recordatorios:
        try:
            total += programar_recordatorio_en_jobqueue(app, rec)
        except Exception:
            logger.exception("Error programando recordatorio %s al boot", rec.id)
    logger.info("Cargados %d recordatorios al JobQueue", total)
    return total


def cargar_recordatorios_al_jobqueue(app: Application) -> None:
    """Wrapper sync: programa la carga inicial via JobQueue.run_once(t=0).

    Se llama desde `registrar_jobs` antes de que el JobQueue arranque, asi
    que no podemos hacer await aqui. Lanzamos un job 1s diferido para
    correr la carga cuando el loop ya este vivo.
    """
    jq = app.job_queue
    if jq is None:
        return

    async def _bootstrap(context) -> None:
        await _cargar_recordatorios_db(context.application)

    jq.run_once(_bootstrap, when=1, name="bootstrap_recordatorios")


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
        dispatch_tick,
        interval=settings.task_dispatcher_interval_seconds,
        first=5,
        name="task_dispatcher_tick",
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

    try:
        from src.telegram.jobs_deportes import registrar_jobs_deportes

        registrar_jobs_deportes(app)
    except Exception:
        logger.exception("Error registrando jobs_deportes")

    try:
        cargar_recordatorios_al_jobqueue(app)
    except Exception:
        logger.exception("Error programando bootstrap de recordatorios personalizados")

    logger.info(
        "Jobs registrados: escalation, dispatcher_tick, quiz_nocturno, quiz_sabado, "
        "checkin, peso_lunes, resumen_domingo, hidratacion_2h, reconsent_militar, "
        "deportes, bootstrap_recordatorios"
    )
