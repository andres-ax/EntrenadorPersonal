"""post_init callback: configura comandos, nombre, descripcion y menu del bot."""
from __future__ import annotations

import logging

from telegram import BotCommand, MenuButtonCommands
from telegram.ext import Application

logger = logging.getLogger(__name__)

COMANDOS_ES: list[BotCommand] = [
    BotCommand("start", "Empezar o saludar"),
    BotCommand("menu", "Acciones rapidas"),
    BotCommand("hoy", "Plan de entreno de hoy"),
    BotCommand("peso", "Registrar mi peso"),
    BotCommand("pr", "Mis Personal Records"),
    BotCommand("reporte", "Mi semana"),
    BotCommand("compromiso", "Ver/firmar compromiso"),
    BotCommand("tono", "Cambiar tono del coach"),
    BotCommand("pausa", "Pausar recordatorios"),
    BotCommand("dia_libre", "Usar un freeze (no rompes streak)"),
    BotCommand("presumir", "Compartir mi PR a un grupo"),
    BotCommand("porque_me_escribiste", "Ver por que te escribi"),
    BotCommand("quiet_hours", "Cambiar mis horas de silencio"),
    BotCommand("apagar_firme", "Bajar tono a amigable"),
    BotCommand("salir", "Salir del modo accountability"),
    BotCommand("feedback", "Calificarme del 1 al 5"),
    BotCommand("ayuda", "Como funciono"),
    BotCommand("reset", "Reiniciar conversacion"),
    BotCommand("borrar_datos", "Eliminar todos mis datos"),
]


BOT_NAME = "EntrenadorAX"
BOT_SHORT_DESC = "Coach AI que no te deja excusas. Entreno, comida, sueno, peso."
BOT_DESC = (
    "Soy EntrenadorAX, tu coach personal con IA dentro de Telegram.\n\n"
    "Te ayudo a:\n"
    "- Registrar entrenamientos, comidas, sueno y peso conversando.\n"
    "- Trackear tus PRs y volumen semanal.\n"
    "- Firmar un compromiso contigo mismo y NO dejarte fallarlo.\n"
    "- Recordarte con el tono que elijas (amigable, firme o militar).\n\n"
    "Solo escribeme, no llenes formularios. /start para empezar."
)


async def setup_bot(app: Application) -> None:
    """Se ejecuta una sola vez al inicio (post_init). Configura identidad del bot."""
    try:
        await app.bot.set_my_commands(COMANDOS_ES, language_code="es")
        await app.bot.set_my_commands(COMANDOS_ES)
        await app.bot.set_my_name(BOT_NAME, language_code="es")
        await app.bot.set_my_short_description(BOT_SHORT_DESC, language_code="es")
        await app.bot.set_my_description(BOT_DESC, language_code="es")
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Bot identity (commands/name/description) configurada")
    except Exception:
        logger.exception("Error configurando identidad del bot")
