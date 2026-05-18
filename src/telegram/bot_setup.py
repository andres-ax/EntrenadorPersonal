"""post_init callback: configura comandos, nombre, descripcion y menu del bot.

Todos los textos vienen de `src.i18n` JSON files (es/en/pt) para mantener una unica fuente.
"""
from __future__ import annotations

import logging

from telegram import BotCommand, MenuButtonCommands, MenuButtonWebApp, WebAppInfo
from telegram.ext import Application

from src.config import settings
from src.i18n import IDIOMAS_SOPORTADOS, t

logger = logging.getLogger(__name__)

# Lista canonica de comandos del bot. La descripcion se traduce via i18n key `cmd_<name>`.
# Cada lang puede omitir comandos avanzados (ej: en/pt solo muestran los basicos).
COMANDOS_CORE = [
    "start",
    "menu",
    "hoy",
    "peso",
    "pr",
    "reporte",
    "compromiso",
    "tono",
    "pausa",
    "dia_libre",
    "pagar",
    "llamar",
    "ayuda",
    "salir",
]

# Set extendido solo para ES (locale principal).
COMANDOS_EXTRA_ES = [
    "presumir",
    "porque_me_escribiste",
    "quiet_hours",
    "apagar_firme",
    "feedback",
    "grafico",
    "exportar_csv",
    "agua",
    "calma",
    "desafios",
    "invitar",
    "reset",
    "borrar_datos",
]

BOT_NAME = "EntrenadorAX"


def _build_commands(lang: str, include_extra: bool = False) -> list[BotCommand]:
    """Construye lista de BotCommand desde i18n keys."""
    nombres = list(COMANDOS_CORE)
    if include_extra:
        nombres.extend(COMANDOS_EXTRA_ES)
    out: list[BotCommand] = []
    for nombre in nombres:
        descripcion = t(f"cmd_{nombre}", lang=lang)
        if not descripcion or descripcion == f"cmd_{nombre}":
            continue
        if len(descripcion) > 256:
            descripcion = descripcion[:253] + "..."
        out.append(BotCommand(nombre, descripcion))
    return out


async def setup_bot(app: Application) -> None:
    """Se ejecuta una sola vez al inicio (post_init). Configura identidad del bot por idioma."""
    bot = app.bot
    try:
        comandos_es = _build_commands("es", include_extra=True)
        await bot.set_my_commands(comandos_es, language_code="es")
        await bot.set_my_commands(comandos_es)
        await bot.set_my_commands(_build_commands("en"), language_code="en")
        await bot.set_my_commands(_build_commands("pt"), language_code="pt")
        logger.info("setMyCommands aplicado a 3 idiomas (es=%d cmds)", len(comandos_es))

        for lang in IDIOMAS_SOPORTADOS:
            try:
                await bot.set_my_name(BOT_NAME, language_code=lang)
                await bot.set_my_short_description(t("bot_short_desc", lang=lang), language_code=lang)
                await bot.set_my_description(t("bot_descripcion", lang=lang), language_code=lang)
            except Exception:
                logger.warning("No pude setear nombre/desc para lang=%s", lang, exc_info=True)

        if settings.miniapp_url:
            try:
                await bot.set_chat_menu_button(
                    menu_button=MenuButtonWebApp(
                        text="App",
                        web_app=WebAppInfo(url=str(settings.miniapp_url)),
                    )
                )
                logger.info("Menu button -> Mini App %s", settings.miniapp_url)
            except Exception:
                logger.exception("Error seteando menu button Mini App")
                await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        else:
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

        logger.info("Bot identity completa configurada para %d idiomas", len(IDIOMAS_SOPORTADOS))
    except Exception:
        logger.exception("Error configurando identidad del bot")
