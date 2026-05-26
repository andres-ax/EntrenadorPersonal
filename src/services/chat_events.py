"""Eventos de chat en tiempo real via Redis pub/sub + FCM fallback."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from src.cache import get_redis
from src.config import settings
from src.db.models import MensajeChat, RolMensajeChat

logger = logging.getLogger(__name__)

WS_ONLINE_TTL = 90


def _channel_user(usuario_id: int) -> str:
    return f"chat:user:{usuario_id}"


def _ws_online_key(usuario_id: int) -> str:
    return f"chat:ws_online:{usuario_id}"


async def mark_ws_online(usuario_id: int) -> None:
    client = await get_redis()
    await client.setex(_ws_online_key(usuario_id), WS_ONLINE_TTL, "1")


async def refresh_ws_online(usuario_id: int) -> None:
    await mark_ws_online(usuario_id)


async def mark_ws_offline(usuario_id: int) -> None:
    client = await get_redis()
    await client.delete(_ws_online_key(usuario_id))


async def is_ws_online(usuario_id: int) -> bool:
    client = await get_redis()
    return bool(await client.get(_ws_online_key(usuario_id)))


def mensaje_event_payload(msg: MensajeChat) -> dict[str, Any]:
    return {
        "id": msg.id,
        "rol": msg.rol.value if msg.rol else "user",
        "contenido": msg.contenido,
        "canal_origen": msg.canal_origen.value if msg.canal_origen else "android",
        "es_desde_telegram": msg.es_desde_telegram,
        "creado_en": msg.creado_en.isoformat() if msg.creado_en else None,
    }


async def publish_chat_event(usuario_id: int, event: dict[str, Any]) -> None:
    if not settings.chat_ws_enabled:
        return
    try:
        client = await get_redis()
        await client.publish(_channel_user(usuario_id), json.dumps(event, ensure_ascii=False))
    except Exception:
        logger.exception("Error publicando chat event user_id=%s", usuario_id)


async def emit_message_new(
    msg: MensajeChat,
    *,
    usuario_id: int,
    conversacion_id: int,
    conversacion_titulo: str | None = None,
) -> None:
    preview = msg.contenido[:120].replace("\n", " ")
    await publish_chat_event(
        usuario_id,
        {
            "type": "message.new",
            "conversacion_id": conversacion_id,
            "conversacion_titulo": conversacion_titulo,
            "mensaje": mensaje_event_payload(msg),
            "ultimo_mensaje_preview": preview,
            "ultimo_mensaje_en": (
                msg.creado_en.isoformat() if msg.creado_en else datetime.utcnow().isoformat()
            ),
        },
    )

    if msg.es_desde_telegram and settings.fcm_enabled:
        if not await is_ws_online(usuario_id):
            from src.services.push_notifications import send_chat_message_push

            await send_chat_message_push(
                usuario_id,
                conversacion_id=conversacion_id,
                preview=preview,
            )


async def emit_conversacion_updated(
    usuario_id: int,
    conversacion_id: int,
    *,
    titulo: str | None = None,
    ultimo_mensaje_preview: str | None = None,
    ultimo_mensaje_en: str | None = None,
) -> None:
    await publish_chat_event(
        usuario_id,
        {
            "type": "conversacion.updated",
            "conversacion_id": conversacion_id,
            "titulo": titulo,
            "ultimo_mensaje_preview": ultimo_mensaje_preview,
            "ultimo_mensaje_en": ultimo_mensaje_en,
        },
    )


async def emit_coach_typing(usuario_id: int, conversacion_id: int, typing: bool = True) -> None:
    await publish_chat_event(
        usuario_id,
        {
            "type": "typing",
            "conversacion_id": conversacion_id,
            "typing": typing,
        },
    )
