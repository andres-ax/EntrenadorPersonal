"""Notificaciones push FCM para mensajes de chat."""
from __future__ import annotations

import json
import logging

from sqlalchemy import delete, select

from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import DevicePushToken

logger = logging.getLogger(__name__)

_firebase_app = None


def _get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    if not settings.fcm_enabled or not settings.firebase_service_account_json:
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials

        if firebase_admin._apps:
            _firebase_app = firebase_admin.get_app()
            return _firebase_app
        cred_dict = json.loads(settings.firebase_service_account_json)
        cred = credentials.Certificate(cred_dict)
        _firebase_app = firebase_admin.initialize_app(cred)
        return _firebase_app
    except Exception:
        logger.exception("No pude inicializar Firebase Admin")
        return None


async def registrar_push_token(
    user_id: int,
    fcm_token: str,
    platform: str = "android",
) -> None:
    token = fcm_token.strip()
    if not token:
        return
    async with async_session_factory() as session:
        await session.execute(
            delete(DevicePushToken).where(DevicePushToken.fcm_token == token)
        )
        row = DevicePushToken(
            usuario_id=user_id,
            fcm_token=token,
            platform=platform[:16],
        )
        session.add(row)
        await session.commit()


async def eliminar_push_token(user_id: int, fcm_token: str) -> None:
    async with async_session_factory() as session:
        await session.execute(
            delete(DevicePushToken).where(
                DevicePushToken.usuario_id == user_id,
                DevicePushToken.fcm_token == fcm_token,
            )
        )
        await session.commit()


async def _tokens_for_user(user_id: int) -> list[str]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(DevicePushToken.fcm_token).where(DevicePushToken.usuario_id == user_id)
        )
        return [row[0] for row in result.all()]


async def send_chat_message_push(
    user_id: int,
    *,
    conversacion_id: int,
    preview: str,
) -> None:
    if not settings.fcm_enabled:
        return
    if _get_firebase_app() is None:
        return
    tokens = await _tokens_for_user(user_id)
    if not tokens:
        return
    try:
        from firebase_admin import messaging

        for token in tokens:
            try:
                message = messaging.Message(
                    token=token,
                    notification=messaging.Notification(
                        title="Coach IA (Telegram)",
                        body=preview[:200],
                    ),
                    data={
                        "type": "chat_message",
                        "conversacion_id": str(conversacion_id),
                        "preview": preview[:200],
                    },
                )
                messaging.send(message)
                logger.info(
                    "FCM chat enviado user_id=%s conv=%s",
                    user_id,
                    conversacion_id,
                )
            except Exception:
                logger.warning("FCM fallo token=%s...", token[:12], exc_info=True)
    except Exception:
        logger.exception("Error enviando FCM user_id=%s", user_id)
