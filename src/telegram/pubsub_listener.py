"""Listener de Redis pubsub para que el bot notifique usuarios.

Canales escuchados:
- pagos_actualizados: admin aprobo/rechazo un pago -> notificar usuario
- broadcast_admin: admin envia mensaje masivo -> filtrar y enviar
"""

from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select

from src.cache import get_redis
from src.db.connection import async_session_factory
from src.db.models import PlanSuscripcion, Usuario
from src.db.repository import PLAN_RANKING, marcar_bot_bloqueado
from telegram.constants import ParseMode
from telegram.ext import Application

logger = logging.getLogger(__name__)

CANAL_PAGOS = "pagos_actualizados"
CANAL_BROADCAST = "broadcast_admin"
CANAL_PR = "pr_publicar_canal"


def _mensaje_pago(tipo: str, payload: dict) -> str | None:
    """Devuelve el mensaje al usuario segun tipo de evento de pago."""
    if tipo == "pago_aprobado":
        plan = payload.get("plan", "starter")
        return (
            f"<b>Pago aprobado!</b> Tu plan <b>{plan}</b> queda activo "
            f"definitivamente. Gracias por confiar."
        )
    if tipo == "pago_rechazado":
        motivo = payload.get("motivo", "no especificado")
        return (
            f"Tu pago no pudo ser validado. Motivo: <i>{motivo}</i>.\n"
            f"Si crees que es un error, contacta soporte respondiendo este mensaje."
        )
    if tipo == "plan_asignado_admin":
        plan = payload.get("plan", "")
        dias = payload.get("dias", 0)
        return f"Un admin te asigno plan <b>{plan}</b> por <b>{dias}</b> dias. " f"Disfruta!"
    return None


async def _enviar_mensaje_seguro(app: Application, chat_id: int, texto: str) -> None:
    try:
        await app.bot.send_message(chat_id=chat_id, text=texto, parse_mode=ParseMode.HTML)
    except Exception as e:
        import telegram.error

        if isinstance(e, telegram.error.Forbidden):
            await marcar_bot_bloqueado(chat_id, True)
            logger.info("Bot bloqueado por %s al notificar evento", chat_id)
            return
        logger.exception("Error notificando uid=%s", chat_id)


async def _procesar_pago(app: Application, raw: str) -> None:
    try:
        data = json.loads(raw)
        uid = int(data.get("telegram_id"))
        tipo = data.get("tipo", "")
        payload = data.get("payload", {})
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Mensaje pubsub pagos invalido: %s", raw[:200])
        return
    texto = _mensaje_pago(tipo, payload)
    if texto:
        await _enviar_mensaje_seguro(app, uid, texto)


async def _procesar_broadcast(app: Application, raw: str) -> None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    mensaje = data.get("mensaje", "")
    if not mensaje:
        return
    plan_minimo_str = data.get("plan_minimo")
    pais = data.get("pais")
    silent = bool(data.get("silent", True))
    plan_minimo_rank = 0
    if plan_minimo_str:
        try:
            plan_minimo_rank = PLAN_RANKING.get(PlanSuscripcion(plan_minimo_str), 0)
        except ValueError:
            pass

    async with async_session_factory() as session:
        query = select(Usuario).where(
            Usuario.onboarding_completo == True,  # noqa: E712
            Usuario.bot_bloqueado == False,  # noqa: E712
        )
        if pais:
            query = query.where(Usuario.pais == pais)
        result = await session.execute(query)
        usuarios = list(result.scalars().all())

    enviados = 0
    for u in usuarios:
        if plan_minimo_rank > 0:
            if PLAN_RANKING.get(u.plan_actual or PlanSuscripcion.FREE, 0) < plan_minimo_rank:
                continue
        try:
            await app.bot.send_message(
                chat_id=u.telegram_id,
                text=mensaje,
                parse_mode=ParseMode.HTML,
                disable_notification=silent,
            )
            enviados += 1
            await asyncio.sleep(0.05)
        except Exception:
            logger.exception("Error en broadcast uid=%s", u.telegram_id)
    logger.info("Broadcast enviado a %s usuarios", enviados)


async def _procesar_pr_canal(app: Application, raw: str) -> None:
    """Publica PR en canal @entrenadorax_logros si user opted-in."""
    import json as _json

    from sqlalchemy import select as _select

    from src.db.models import PersonalRecord as _PR
    from src.services.canal_logros import publicar_pr

    try:
        data = _json.loads(raw)
        pr_id = int(data["pr_id"])
        telegram_id = int(data["telegram_id"])
    except (json.JSONDecodeError, ValueError, KeyError):
        return
    async with async_session_factory() as session:
        result = await session.execute(_select(_PR).where(_PR.id == pr_id))
        pr = result.scalar_one_or_none()
    if pr is None:
        return
    try:
        await publicar_pr(app.bot, telegram_id, pr)
    except Exception:
        logger.exception("Error publicar_pr uid=%s", telegram_id)


async def _listener_loop(app: Application) -> None:
    client = await get_redis()
    pubsub = client.pubsub()
    await pubsub.subscribe(CANAL_PAGOS, CANAL_BROADCAST, CANAL_PR)
    logger.info(
        "Pubsub listener escuchando %s + %s + %s",
        CANAL_PAGOS,
        CANAL_BROADCAST,
        CANAL_PR,
    )
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            canal = message.get("channel", "")
            raw = message.get("data", "")
            if canal == CANAL_PAGOS:
                await _procesar_pago(app, raw)
            elif canal == CANAL_BROADCAST:
                await _procesar_broadcast(app, raw)
            elif canal == CANAL_PR:
                await _procesar_pr_canal(app, raw)
    except asyncio.CancelledError:
        logger.info("Pubsub listener cancelado")
        raise
    except Exception:
        logger.exception("Pubsub listener crash")
    finally:
        try:
            await pubsub.unsubscribe()
            await pubsub.aclose()
        except Exception:
            logger.exception("Error cerrando pubsub listener")


def start_pubsub_listener(app: Application) -> asyncio.Task:
    """Arranca el listener como task de fondo. Devuelve el task para cancelar."""
    return asyncio.create_task(_listener_loop(app))
