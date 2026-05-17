"""Handlers de Telegram: comandos, mensajes, callbacks, foto."""
from __future__ import annotations

import asyncio
import logging
from datetime import date

import telegram.error
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agents import RunConfig, Runner, SessionSettings
from agents.extensions.memory import RedisSession

from src.cache import limpiar_keys_usuario
from src.coach import coach
from src.config import settings
from src.db.repository import (
    eliminar_usuario,
    log_evento,
    marcar_bot_bloqueado,
    obtener_o_crear_usuario,
    obtener_usuario,
)
from src.telegram.middlewares import check_rate_limit

logger = logging.getLogger(__name__)

RUN_CONFIG = RunConfig(session_settings=SessionSettings(limit=settings.session_limit))


async def _enviar_con_retry(message, texto: str, intentos: int = 3, **kwargs) -> None:
    """Envia un mensaje con retry exponencial. Marca bot_bloqueado en Forbidden."""
    for i in range(intentos):
        try:
            await message.reply_text(texto, **kwargs)
            return
        except telegram.error.TimedOut:
            if i == intentos - 1:
                raise
            await asyncio.sleep(1.5**i)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            if i == intentos - 1:
                raise
        except telegram.error.Forbidden:
            uid = getattr(message.chat, "id", None)
            if uid is not None:
                await marcar_bot_bloqueado(uid, True)
            logger.info("Bot bloqueado por uid=%s", uid)
            return


async def _build_prompt(texto: str, uid: int) -> str:
    """Construye el prompt con perfil + tono + compromiso + streak inyectados."""
    user = await obtener_o_crear_usuario(uid)
    perfil_parts = [
        f"uid={uid}",
        f"fecha={date.today().isoformat()}",
        f"tono={user.tono.value if user.tono else 'firme'}",
    ]
    if user.nombre:
        perfil_parts.append(f"nombre={user.nombre}")
    if user.peso_kg:
        perfil_parts.append(f"peso={user.peso_kg}kg")
    if user.altura_cm:
        perfil_parts.append(f"altura={user.altura_cm}cm")
    if user.edad:
        perfil_parts.append(f"edad={user.edad}")
    if user.objetivo:
        perfil_parts.append(f"objetivo={user.objetivo}")
    if user.nivel:
        perfil_parts.append(f"nivel={user.nivel}")
    if user.dias_entreno:
        perfil_parts.append(f"dias_entreno={user.dias_entreno}")
    if user.deporte_principal:
        perfil_parts.append(f"deporte={user.deporte_principal}")
    perfil_parts.append(
        f"onboarding={'si' if user.onboarding_completo else 'no'}"
    )
    return f"[{' | '.join(perfil_parts)}] {texto}"


async def _procesar(message, texto: str, uid: int) -> None:
    """Ejecuta el agente con sesion Redis. Sesion DB cerrada antes del LLM."""
    prompt = await _build_prompt(texto, uid)
    session = RedisSession.from_url(
        str(uid),
        url=settings.redis_url_str,
        ttl=settings.session_ttl_seconds,
    )
    try:
        result = await Runner.run(
            coach, prompt, session=session, run_config=RUN_CONFIG
        )
        output = result.final_output
        for i in range(0, len(output), 4000):
            await _enviar_con_retry(message, output[i : i + 4000])
    except Exception:
        logger.exception("Error procesando mensaje uid=%s", uid)
        await _enviar_con_retry(
            message, "Ups, tuve un problema procesando tu mensaje. Intentalo de nuevo."
        )
    finally:
        await session.close()


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    nombre = update.effective_user.first_name
    if not await check_rate_limit(uid):
        await update.message.reply_text(
            "Tranquilo, dame un segundo. Estoy procesando lo anterior."
        )
        return
    await obtener_o_crear_usuario(uid, nombre)
    await log_evento(uid, "start", {"nombre": nombre})
    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(update.message, "Hola, quiero empezar!", uid)


async def mensaje(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    texto = update.message.text or ""
    if len(texto) > settings.max_message_chars:
        await update.message.reply_text(
            f"Mensaje muy largo (limite {settings.max_message_chars} chars). Resume."
        )
        return
    if not await check_rate_limit(uid):
        await update.message.reply_text(
            "Tranquilo, estoy procesando. Espera un momento."
        )
        return
    await update.message.chat.send_action(ChatAction.TYPING)
    await _procesar(update.message, texto, uid)


async def menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Registrar entreno", callback_data="entreno"),
            InlineKeyboardButton("Registrar comida", callback_data="comida"),
        ],
        [
            InlineKeyboardButton("Como dormi", callback_data="sueno"),
            InlineKeyboardButton("Mi peso actual", callback_data="peso"),
        ],
        [
            InlineKeyboardButton("Reporte semanal", callback_data="reporte"),
            InlineKeyboardButton("Historial de peso", callback_data="historial_peso"),
        ],
    ]
    await update.message.reply_text(
        "Que quieres hacer?", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Limpia la sesion de Redis del usuario para resolver historial corrupto."""
    uid = update.effective_user.id
    try:
        n = await limpiar_keys_usuario(uid)
        await log_evento(uid, "reset", {"keys_borradas": n})
        await update.message.reply_text(
            "Listo! Tu sesion fue reiniciada. Escribe /start para comenzar de nuevo."
        )
    except Exception:
        logger.exception("Error reseteando sesion uid=%s", uid)
        await update.message.reply_text(
            "No pude reiniciar la sesion. Intenta de nuevo en un momento."
        )


async def borrar_datos(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton(
                "Si, borrar TODOS mis datos", callback_data="confirmar_borrado"
            )
        ]
    ]
    await update.message.reply_text(
        "Esto eliminara permanentemente TODOS tus datos:\n"
        "- Perfil y onboarding\n"
        "- Entrenamientos y PRs\n"
        "- Comidas y nutricion\n"
        "- Sueno y metricas corporales\n"
        "- Historial conversacional\n\n"
        "Esta accion NO se puede deshacer. Estas seguro?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def boton(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "confirmar_borrado":
        try:
            borrado = await eliminar_usuario(uid)
            await limpiar_keys_usuario(uid)
            await log_evento(uid, "borrar_datos", {"existia": borrado})
            if borrado:
                await q.edit_message_text(
                    "Todos tus datos han sido eliminados permanentemente. "
                    "Usa /start para comenzar desde cero."
                )
            else:
                await q.edit_message_text(
                    "No encontre datos asociados a tu cuenta. "
                    "Usa /start para empezar."
                )
        except Exception:
            logger.exception("Error borrando datos uid=%s", uid)
            await q.edit_message_text(
                "Hubo un error eliminando tus datos. Intenta de nuevo en un momento."
            )
        return

    mapping = {
        "onboarding": "Hola, quiero empezar!",
        "entreno": "Quiero registrar mi entrenamiento de hoy",
        "comida": "Quiero registrar lo que comi hoy",
        "sueno": "Quiero registrar como dormi anoche",
        "peso": "Quiero registrar mi peso actual",
        "reporte": "Como voy esta semana? Dame mi reporte",
        "historial_peso": "Muestrame mi historial de peso",
    }
    texto = mapping.get(q.data, "Hola")
    await q.message.chat.send_action(ChatAction.TYPING)
    await _procesar(q.message, texto, uid)


def registrar(app: Application) -> None:
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("borrar_datos", borrar_datos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje))
    app.add_handler(CallbackQueryHandler(boton))
