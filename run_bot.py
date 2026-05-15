#!/usr/bin/env python
"""Inicia el bot EntrenadorAX en modo polling (desarrollo local)."""
import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from telegram.ext import Application
from src.db.connection import close_db, init_db
from src.telegram.handlers import registrar
from src.telegram.scheduler import registrar_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Inicializando base de datos...")
    await init_db()
    logger.info("Base de datos lista.")

    app = Application.builder().token(os.getenv("TELEGRAM_TOKEN")).build()
    registrar(app)
    registrar_jobs(app)

    await app.initialize()
    await app.start()
    logger.info("Bot iniciado! Habla con el bot en Telegram.")
    await app.updater.start_polling(drop_pending_updates=True)

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Deteniendo bot...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await close_db()


if __name__ == "__main__":
    asyncio.run(main())
