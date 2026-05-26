"""Tests Redis pub/sub chat events."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.db.models import CanalConversacion, MensajeChat, RolMensajeChat
from src.services.chat_events import emit_message_new, publish_chat_event


@pytest.mark.asyncio
async def test_publish_chat_event(mock_redis, monkeypatch):
    published: list[tuple[str, str]] = []

    async def fake_publish(channel, message):
        published.append((channel, message))

    mock_redis.publish = fake_publish
    monkeypatch.setattr("src.services.chat_events.get_redis", AsyncMock(return_value=mock_redis))

    await publish_chat_event(42, {"type": "message.new", "conversacion_id": 1})
    assert len(published) == 1
    assert published[0][0] == "chat:user:42"
    payload = json.loads(published[0][1])
    assert payload["type"] == "message.new"


@pytest.mark.asyncio
async def test_emit_message_new_fcm_when_offline(mock_redis, monkeypatch):
    mock_redis.publish = AsyncMock()
    monkeypatch.setattr("src.services.chat_events.get_redis", AsyncMock(return_value=mock_redis))
    monkeypatch.setattr("src.services.chat_events.settings.fcm_enabled", True)
    monkeypatch.setattr("src.services.chat_events.is_ws_online", AsyncMock(return_value=False))

    push_mock = AsyncMock()
    monkeypatch.setattr("src.services.push_notifications.send_chat_message_push", push_mock)

    msg = MensajeChat(
        id=99,
        conversacion_id=5,
        rol=RolMensajeChat.ASSISTANT,
        contenido="Hola desde TG",
        canal_origen=CanalConversacion.TELEGRAM,
        es_desde_telegram=True,
    )
    await emit_message_new(msg, usuario_id=7, conversacion_id=5, conversacion_titulo="Coach")
    push_mock.assert_awaited_once()
