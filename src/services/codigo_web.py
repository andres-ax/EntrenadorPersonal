"""Login web del deportista via codigo de 6 digitos generado por el bot.

Flujo:
1. Usuario manda /codigo_web al bot Telegram.
2. Bot llama `generar_codigo(telegram_id)` que crea un codigo aleatorio
   de 6 digitos, lo guarda en Redis con key `codigo_web:<codigo>` -> uid
   con TTL 15 min. Si ya existia un codigo previo del mismo usuario, lo
   invalida (key `codigo_web:uid:<uid>` -> codigo).
3. El bot envia el codigo al usuario por chat.
4. El usuario abre la landing `/login`, tab "Deportista", pega el codigo
   y POST /api/auth/codigo. Si es valido, se setea cookie HttpOnly
   `user_jwt` y se redirige a `/app/`.

Por que no email/magic-links: Telegram es la unica fuente de verdad de
identidad. No todos los usuarios tienen email registrado. El codigo
corto es facil de pegar desde el celular.
"""

from __future__ import annotations

import logging
import secrets

from src.cache import get_redis

logger = logging.getLogger(__name__)


CODIGO_TTL_SECONDS = 15 * 60  # 15 minutos
CODIGO_KEY = "codigo_web:{codigo}"
# Key inversa: uid -> codigo activo. Permite invalidar el anterior cuando
# el usuario pide un codigo nuevo (un solo codigo activo por usuario).
UID_KEY = "codigo_web:uid:{uid}"


def _generar_codigo_aleatorio() -> str:
    """Genera 6 digitos con secrets.randbelow (uniformemente distribuido)."""
    return f"{secrets.randbelow(1_000_000):06d}"


async def generar_codigo(telegram_id: int) -> str:
    """Genera un nuevo codigo de 6 digitos para el usuario.

    Invalida cualquier codigo previo del mismo usuario. Devuelve el codigo
    en texto plano (el llamador debe enviarlo al usuario, no se almacena
    en texto plano fuera de Redis).
    """
    client = await get_redis()
    codigo = _generar_codigo_aleatorio()
    # Si el usuario ya tenia un codigo activo, borralo
    codigo_previo = await client.get(UID_KEY.format(uid=telegram_id))
    if codigo_previo:
        try:
            await client.delete(CODIGO_KEY.format(codigo=codigo_previo))
        except Exception:
            logger.exception("Error borrando codigo previo uid=%s", telegram_id)
    # Guardar nuevo codigo en ambas direcciones (codigo -> uid, uid -> codigo)
    await client.setex(CODIGO_KEY.format(codigo=codigo), CODIGO_TTL_SECONDS, str(telegram_id))
    await client.setex(UID_KEY.format(uid=telegram_id), CODIGO_TTL_SECONDS, codigo)
    logger.info(
        "codigo_web generado uid=%s codigo=******%s ttl=%ds",
        telegram_id,
        codigo[-2:],
        CODIGO_TTL_SECONDS,
    )
    return codigo


async def validar_y_consumir(codigo: str) -> int | None:
    """Valida un codigo y lo elimina si es correcto (single-use).

    Returns
    -------
        telegram_id si el codigo es valido y no estaba expirado.
        None si no existe, expiro, o ya fue usado.

    """
    if not codigo or not codigo.isdigit() or len(codigo) != 6:
        return None
    client = await get_redis()
    uid_str = await client.get(CODIGO_KEY.format(codigo=codigo))
    if not uid_str:
        return None
    try:
        uid = int(uid_str)
    except (TypeError, ValueError):
        return None
    # Single use: borrar inmediatamente ambas keys
    try:
        await client.delete(
            CODIGO_KEY.format(codigo=codigo),
            UID_KEY.format(uid=uid),
        )
    except Exception:
        logger.exception("Error borrando codigo despues de uso uid=%s", uid)
    logger.info("codigo_web consumido uid=%s", uid)
    return uid
