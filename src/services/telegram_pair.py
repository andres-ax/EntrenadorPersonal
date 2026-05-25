"""Vinculacion app movil <-> cuenta Telegram.

Flujo recomendado:
1. App autenticada pide POST /api/me/telegram/pair-token.
2. Usuario abre Telegram y envia `/vincular <codigo_6_digitos>` al bot
   (alternativa: deep link t.me/bot?start=pair_<token>).
3. Bot asocia telegram_id real al usuario de la app.
4. App llama POST /api/me/telegram/finish-pair para refrescar el JWT
   (el subject pasa del telegram_id virtual negativo al real).
"""
from __future__ import annotations

import json
import logging
import secrets

from src.cache import get_redis
from src.db.connection import async_session_factory
from src.db.models import Usuario
from src.services.identity import link_telegram_to_user
from sqlalchemy import select

logger = logging.getLogger(__name__)

PAIR_TTL_SECONDS = 600
PAIR_TOKEN_PREFIX = "telegram:pair:"
PAIR_CODE_PREFIX = "telegram:pair:code:"
JWT_REFRESH_PREFIX = "telegram:pair:refresh:"
JWT_SUB_USER_PREFIX = "telegram:pair:jwt_sub_user:"


async def _obtener_usuario_por_id(user_id: int) -> Usuario | None:
    async with async_session_factory() as session:
        result = await session.execute(select(Usuario).where(Usuario.id == user_id))
        return result.scalar_one_or_none()


def _generar_codigo_6() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


async def crear_solicitud_vinculacion(user_id: int, jwt_sub: int) -> dict:
    """Crea token deep-link + codigo /vincular de 6 digitos."""
    client = await get_redis()
    pair_token = f"pair_{secrets.token_hex(8)}"
    pair_code = _generar_codigo_6()
    while await client.get(f"{PAIR_CODE_PREFIX}{pair_code}"):
        pair_code = _generar_codigo_6()

    payload = json.dumps(
        {
            "user_id": user_id,
            "jwt_sub": jwt_sub,
            "pair_token": pair_token,
            "pair_code": pair_code,
        }
    )
    await client.setex(f"{PAIR_TOKEN_PREFIX}{pair_token}", PAIR_TTL_SECONDS, payload)
    await client.setex(f"{PAIR_CODE_PREFIX}{pair_code}", PAIR_TTL_SECONDS, payload)
    await client.setex(f"{JWT_SUB_USER_PREFIX}{jwt_sub}", PAIR_TTL_SECONDS, str(user_id))

    return {
        "pair_token": pair_token,
        "pair_code": pair_code,
        "expires_in": PAIR_TTL_SECONDS,
    }


async def _resolver_payload(ref: str) -> dict | None:
    client = await get_redis()
    raw: str | None
    if ref.startswith("pair_"):
        raw = await client.get(f"{PAIR_TOKEN_PREFIX}{ref}")
    elif ref.isdigit() and len(ref) == 6:
        raw = await client.get(f"{PAIR_CODE_PREFIX}{ref}")
    else:
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def _limpiar_solicitud(payload: dict) -> None:
    client = await get_redis()
    pair_token = payload.get("pair_token")
    pair_code = payload.get("pair_code")
    if pair_token:
        await client.delete(f"{PAIR_TOKEN_PREFIX}{pair_token}")
    if pair_code:
        await client.delete(f"{PAIR_CODE_PREFIX}{pair_code}")


async def ejecutar_vinculacion(pair_ref: str, telegram_id: int) -> Usuario | None:
    """Vincula telegram_id al usuario de la app. Retorna Usuario actualizado o None."""
    payload = await _resolver_payload(pair_ref)
    if not payload:
        return None

    user_id = int(payload["user_id"])
    jwt_sub = int(payload["jwt_sub"])

    user = await _obtener_usuario_por_id(user_id)
    if user is None:
        return None

    old_jwt_sub = user.telegram_id if user.telegram_id is not None else jwt_sub
    linked = await link_telegram_to_user(user_id, telegram_id)

    client = await get_redis()
    await client.setex(
        f"{JWT_REFRESH_PREFIX}{old_jwt_sub}",
        PAIR_TTL_SECONDS,
        str(telegram_id),
    )
    await client.setex(
        f"{JWT_REFRESH_PREFIX}user:{user_id}",
        PAIR_TTL_SECONDS,
        str(telegram_id),
    )
    await _limpiar_solicitud(payload)

    logger.info(
        "telegram vinculado user_id=%s telegram_id=%s jwt_sub_anterior=%s",
        user_id,
        telegram_id,
        old_jwt_sub,
    )
    return linked


async def consumir_refresh_jwt(jwt_sub: int) -> int | None:
    """Si hay vinculacion reciente, devuelve el nuevo telegram_id para re-firmar JWT."""
    client = await get_redis()
    raw = await client.get(f"{JWT_REFRESH_PREFIX}{jwt_sub}")
    if not raw:
        return None
    await client.delete(f"{JWT_REFRESH_PREFIX}{jwt_sub}")
    await client.delete(f"{JWT_SUB_USER_PREFIX}{jwt_sub}")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def consumir_refresh_jwt_por_user_id(user_id: int) -> int | None:
    """Fallback cuando el JWT aún tiene subject virtual pero la fila ya cambió."""
    client = await get_redis()
    key = f"{JWT_REFRESH_PREFIX}user:{user_id}"
    raw = await client.get(key)
    if not raw:
        return None
    await client.delete(key)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def limpiar_jwt_sub_user(jwt_sub: int) -> None:
    client = await get_redis()
    await client.delete(f"{JWT_SUB_USER_PREFIX}{jwt_sub}")


async def resolver_user_id_desde_jwt_sub(jwt_sub: int) -> int | None:
    """Mapeo temporal jwt_sub (virtual) -> user.id interno."""
    client = await get_redis()
    raw = await client.get(f"{JWT_SUB_USER_PREFIX}{jwt_sub}")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
