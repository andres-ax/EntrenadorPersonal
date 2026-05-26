"""Tests handoff app -> Telegram."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models import CanalConversacion, Conversacion, MensajeChat, RolMensajeChat, Usuario
from src.services.conversation_handoff import handoff_app_a_telegram


@pytest.mark.asyncio
async def test_handoff_genera_resumen_y_notifica(db_session, mock_redis, monkeypatch):
    user = Usuario(telegram_id=77001, nombre="Hand", telefono="+573007776655", email="h@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conv = Conversacion(
        usuario_id=user.id,
        titulo="Plan fuerza",
        canal_creador=CanalConversacion.ANDROID,
        activa=True,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    msg = MensajeChat(
        conversacion_id=conv.id,
        rol=RolMensajeChat.USER,
        contenido="Quiero subir sentadilla",
        canal_origen=CanalConversacion.ANDROID,
    )
    db_session.add(msg)
    await db_session.commit()

    async def _fake_get_redis():
        return mock_redis

    monkeypatch.setattr("src.cache.get_redis", _fake_get_redis)
    monkeypatch.setattr("src.services.conversation_service.get_redis", _fake_get_redis)
    monkeypatch.setattr(
        "src.services.conversation_handoff._generar_resumen_handoff",
        AsyncMock(return_value="Resumen de prueba del hilo."),
    )
    monkeypatch.setattr(
        "src.services.conversation_handoff.SafeRedisSession.from_url",
        MagicMock(return_value=MagicMock(add_items=AsyncMock(), close=AsyncMock())),
    )

    bot = MagicMock()
    bot.send_message = AsyncMock()

    result = await handoff_app_a_telegram(conv.id, user.id, user.telegram_id, bot)

    assert result["ok"] is True
    assert result["resumen"] == "Resumen de prueba del hilo."
    bot.send_message.assert_awaited_once()
