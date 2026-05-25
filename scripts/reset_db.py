"""Recrea TODAS las tablas. SOLO PARA DESARROLLO. Destruye todos los datos."""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from sqlalchemy import text

if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("PRODUCTION"):
    logging.error("ERROR: Este script NO debe ejecutarse en produccion.")
    sys.exit(1)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from src.db.connection import engine  # noqa: E402
from src.db.models import Base  # noqa: E402


async def reset_db():
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS ejercicios_realizados CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS sesiones_entrenamiento CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS comidas CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS personal_records CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS metricas_sueno CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS metricas_corporales CASCADE"))
        await conn.execute(text("DROP TABLE IF EXISTS usuarios CASCADE"))
        logging.info("Tablas eliminadas")
        await conn.run_sync(Base.metadata.create_all)
        logging.info("Tablas recreadas")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(reset_db())
