"""post_init callback: configura comandos, nombre, descripcion y menu del bot."""
from __future__ import annotations

import logging

from telegram import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo
from telegram.ext import Application

from src.config import settings

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
    BotCommand("grafico", "Ver charts (peso/volumen/macros/streak/resumen)"),
    BotCommand("exportar_csv", "Descargar mis entrenos en CSV"),
    BotCommand("llamar", "Llamar al coach por voz (Pro)"),
    BotCommand("pagar", "Ver planes y pagar (desde $5.000)"),
    BotCommand("agua", "Registrar agua / ver hidratacion"),
    BotCommand("calma", "Sesion de mindfulness"),
    BotCommand("desafios", "Desafios semanales de la comunidad"),
    BotCommand("invitar", "Invitar amigos (referido)"),
    BotCommand("ayuda", "Como funciono"),
    BotCommand("reset", "Reiniciar conversacion"),
    BotCommand("borrar_datos", "Eliminar todos mis datos"),
]

COMANDOS_EN: list[BotCommand] = [
    BotCommand("start", "Start or say hi"),
    BotCommand("menu", "Quick actions"),
    BotCommand("hoy", "Today's plan"),
    BotCommand("peso", "Log my weight"),
    BotCommand("pr", "My Personal Records"),
    BotCommand("reporte", "Weekly report"),
    BotCommand("tono", "Change coach tone"),
    BotCommand("pausa", "Pause reminders"),
    BotCommand("llamar", "Voice call coach (Pro)"),
    BotCommand("pagar", "Plans (from COP 5,000)"),
    BotCommand("ayuda", "Help"),
    BotCommand("borrar_datos", "Delete all my data"),
]

COMANDOS_PT: list[BotCommand] = [
    BotCommand("start", "Comecar ou cumprimentar"),
    BotCommand("menu", "Acoes rapidas"),
    BotCommand("hoy", "Plano de hoje"),
    BotCommand("peso", "Registrar peso"),
    BotCommand("pr", "Meus PRs"),
    BotCommand("reporte", "Relatorio semanal"),
    BotCommand("tono", "Mudar tom do coach"),
    BotCommand("pagar", "Planos (desde R$ poucos)"),
    BotCommand("ayuda", "Como funciono"),
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
        await app.bot.set_my_commands(COMANDOS_EN, language_code="en")
        await app.bot.set_my_commands(COMANDOS_PT, language_code="pt")
        await app.bot.set_my_commands(COMANDOS_ES)
        await app.bot.set_my_name(BOT_NAME, language_code="es")
        await app.bot.set_my_short_description(BOT_SHORT_DESC, language_code="es")
        await app.bot.set_my_description(BOT_DESC, language_code="es")

        if settings.miniapp_url:
            try:
                await app.bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="App",
                        web_app=WebAppInfo(url=str(settings.miniapp_url)),
                    )
                )
                logger.info("Menu button -> Mini App %s", settings.miniapp_url)
            except Exception:
                logger.exception("Error seteando menu button Mini App")
                await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        else:
            await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Bot identity (commands/name/description) configurada")
    except Exception:
        logger.exception("Error configurando identidad del bot")
