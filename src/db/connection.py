"""Engine y session factory async para PostgreSQL via asyncpg."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)

from src.config import settings
from src.db.models import Base

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url_str,
    echo=(settings.env == "dev"),
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,
    pool_recycle=settings.db_pool_recycle,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Crea tablas si no existen. SKIP en prod (usar `alembic upgrade head`)."""
    if settings.is_prod:
        logger.info(
            "env=prod: skip create_all, alembic upgrade head debe correrse fuera"
        )
        return
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Cierra el engine al shutdown."""
    await engine.dispose()


async def ping() -> bool:
    """Healthcheck de Postgres (uso en /health)."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.exception("DB ping failed")
        return False
