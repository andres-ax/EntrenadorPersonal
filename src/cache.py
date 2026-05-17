"""Cliente Redis async centralizado.

Singleton compartido entre:
- src/telegram/middlewares.py (rate limit, sorted sets)
- src/telegram/handlers.py (limpieza de sesion del agente)
- src/coach session (RedisSession del SDK puede inyectar este cliente)

Centraliza para evitar:
- Leaks de conexiones (cada from_url crea un pool nuevo)
- Race conditions en singletons globales
- Deprecation warnings (close() -> aclose())
"""
from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

from src.config import settings

logger = logging.getLogger(__name__)

_client: aioredis.Redis | None = None
_lock = asyncio.Lock()


async def get_redis() -> aioredis.Redis:
    """Devuelve el cliente Redis singleton, thread-safe via asyncio.Lock."""
    global _client
    if _client is not None:
        return _client
    async with _lock:
        if _client is None:
            _client = aioredis.from_url(
                settings.redis_url_str,
                decode_responses=True,
                health_check_interval=30,
                socket_keepalive=True,
                retry_on_timeout=True,
            )
            logger.info("Redis client inicializado")
    return _client


async def close_redis() -> None:
    """Cierra el cliente al shutdown del proceso."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            logger.exception("Error cerrando Redis")
        finally:
            _client = None


async def limpiar_keys_usuario(uid: int) -> int:
    """Elimina todas las keys de sesion del agente para un usuario.

    Returns:
        Numero de keys eliminadas.
    """
    client = await get_redis()
    keys: list[str] = []
    async for key in client.scan_iter(f"agents:session:{uid}*"):
        keys.append(key)
    if not keys:
        return 0
    return await client.delete(*keys)


async def ping() -> bool:
    """Healthcheck de Redis (uso en /health)."""
    try:
        client = await get_redis()
        return bool(await client.ping())
    except Exception:
        logger.exception("Redis ping failed")
        return False
