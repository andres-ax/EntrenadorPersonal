"""Inicia el bot EntrenadorAX en modo polling (desarrollo local)."""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from telegram.constants import ParseMode  # noqa: E402
from telegram.ext import Application, Defaults  # noqa: E402

from src.cache import close_redis  # noqa: E402
from src.config import settings  # noqa: E402
from src.db.connection import close_db, init_db  # noqa: E402
from src.telegram.bot_setup import setup_bot  # noqa: E402
from src.telegram.handlers import registrar  # noqa: E402
from src.telegram.scheduler import registrar_jobs  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def _stop_when_signaled() -> None:
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass
    await stop_event.wait()


async def main() -> None:
    logger.info("Inicializando base de datos...")
    await init_db()
    try:
        from src.db.repository import cargar_catalog_en_cache

        n = await cargar_catalog_en_cache()
        logger.info("Cargados %s deportes en cache", n)
    except Exception:
        logger.exception("No pude precargar catalog de deportes")
    logger.info("Base de datos lista.")

    defaults = Defaults(
        parse_mode=ParseMode.HTML,
        tzinfo=ZoneInfo(settings.default_timezone),
    )

    app: Application = (
        Application.builder()
        .token(settings.telegram_token.get_secret_value())
        .defaults(defaults)
        .post_init(setup_bot)
        .build()
    )
    registrar(app)
    registrar_jobs(app)

    await app.initialize()
    await app.start()
    logger.info("Bot iniciado en polling. Habla con el bot en Telegram.")
    await app.updater.start_polling(
        drop_pending_updates=True,
        allowed_updates=[
            "message",
            "callback_query",
            "poll_answer",
            "message_reaction",
            "pre_checkout_query",
        ],
    )

    try:
        await _stop_when_signaled()
    finally:
        logger.info("Deteniendo bot...")
        try:
            await app.updater.stop()
        except Exception:
            logger.exception("Error stop updater")
        await app.stop()
        await app.shutdown()
        await close_db()
        await close_redis()
        logger.info("Bot detenido. Bye.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
