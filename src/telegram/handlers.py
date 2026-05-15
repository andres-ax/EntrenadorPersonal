import asyncio
import logging
from datetime import date

import redis.asyncio as aioredis
import telegram.error
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from agents import RunConfig, Runner, SessionSettings
from agents.extensions.memory import RedisSession

from src.coach import coach
from src.config import settings
from src.db.repository import eliminar_usuario, obtener_o_crear_usuario
from src.telegram.middlewares import check_rate_limit

logger = logging.getLogger(__name__)

RUN_CONFIG = RunConfig(session_settings=SessionSettings(limit=20))


async def _enviar_con_retry(message, texto: str, intentos: int = 3):
    """Envia un mensaje con retry exponencial para manejar timeouts de red."""
    for i in range(intentos):
        try:
            await message.reply_text(texto)
            return
        except telegram.error.TimedOut:
            if i == intentos - 1:
                raise
            await asyncio.sleep(1.5 ** i)
        except telegram.error.RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            if i == intentos - 1:
                raise


async def _build_prompt(texto: str, uid: int) -> str:
    """Construye el prompt con perfil inyectado para ahorrar una llamada al agente."""
    user = await obtener_o_crear_usuario(uid)
    perfil_parts = [f"uid={uid}", f"fecha={date.today().isoformat()}"]
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
    perfil_parts.append(f"onboarding={'si' if user.onboarding_completo else 'no'}")
    return f"[{' | '.join(perfil_parts)}] {texto}"


async def _procesar(message, texto: str, uid: int):
    """Ejecuta el agente OpenAI con contexto del usuario."""
    prompt = await _build_prompt(texto, uid)
    session = RedisSession.from_url(str(uid), url=settings.redis_url)
    try:
        result = await Runner.run(
            coach, prompt, session=session, run_config=RUN_CONFIG
        )
        output = result.final_output
        for i in range(0, len(output), 4000):
            await _enviar_con_retry(message, output[i:i + 4000])
    except Exception as e:
        logger.exception("Error procesando mensaje uid=%s", uid)
        await _enviar_con_retry(
            message, "Ups, tuve un problema procesando tu mensaje. Intentalo de nuevo."
        )
    finally:
        await session.close()


async def start(update: Update, ctx):
    uid = update.effective_user.id
    nombre = update.effective_user.first_name
    await obtener_o_crear_usuario(uid, nombre)
    await update.message.chat.send_action("typing")
    await _procesar(update.message, "Hola, quiero empezar!", uid)


async def mensaje(update: Update, ctx):
    uid = update.effective_user.id
    if not await check_rate_limit(uid):
        await update.message.reply_text("Tranquilo, estoy procesando. Espera un momento.")
        return
    await update.message.chat.send_action("typing")
    await _procesar(update.message, update.message.text, uid)


async def _limpiar_redis(uid: int):
    """Elimina todas las keys de sesion del usuario en Redis."""
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    keys = []
    async for key in client.scan_iter(f"agents:session:{uid}*"):
        keys.append(key)
    if keys:
        await client.delete(*keys)
    await client.close()


async def menu(update: Update, ctx):
    """Muestra un menu rapido con botones inline."""
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


async def reset(update: Update, ctx):
    """Limpia la sesion de Redis del usuario para resolver historial corrupto."""
    uid = update.effective_user.id
    try:
        await _limpiar_redis(uid)
        await update.message.reply_text(
            "Listo! Tu sesion fue reiniciada. Escribe /start para comenzar de nuevo."
        )
    except Exception as e:
        logger.exception("Error reseteando sesion uid=%s", uid)
        await update.message.reply_text(
            "No pude reiniciar la sesion. Intenta de nuevo en un momento."
        )


async def borrar_datos(update: Update, ctx):
    """Muestra advertencia y boton de confirmacion para eliminar todos los datos."""
    keyboard = [[InlineKeyboardButton(
        "Si, borrar TODOS mis datos", callback_data="confirmar_borrado"
    )]]
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


async def boton(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "confirmar_borrado":
        try:
            borrado = await eliminar_usuario(uid)
            await _limpiar_redis(uid)
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
        except Exception as e:
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
    await q.message.chat.send_action("typing")
    await _procesar(q.message, texto, uid)


def registrar(app: Application):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("borrar_datos", borrar_datos))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje))
    app.add_handler(CallbackQueryHandler(boton))
