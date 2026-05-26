"""Tests API REST chat."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.api.auth import _sign_jwt
from src.db.models import CanalConversacion, Conversacion, Usuario
from src.services.coach_turn import CoachTurnResult


@pytest.mark.asyncio
async def test_chat_api_enviar_mensaje(api_client, db_session, mock_redis):
    user = Usuario(telegram_id=88001, nombre="Chat", telefono="+573009998877", email="c@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conv = Conversacion(
        usuario_id=user.id,
        titulo="Entreno",
        canal_creador=CanalConversacion.ANDROID,
        activa=True,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    token = _sign_jwt(user.telegram_id)
    headers = {"Authorization": f"Bearer {token}"}

    mock_result = CoachTurnResult(
        respuesta="Perfecto, vamos.",
        mensaje_usuario_id=1,
        mensaje_coach_id=2,
        request_id="abc",
    )

    with (
        patch("src.api.chat.run_coach_turn", AsyncMock(return_value=mock_result)),
        patch("src.api.chat.check_rate_limit", AsyncMock(return_value=True)),
        patch("src.api.chat.check_daily_quota", AsyncMock(return_value=(True, 1, 25))),
    ):
        response = await api_client.post(
            f"/api/me/conversaciones/{conv.id}/chat",
            json={"mensaje": "Que toca hoy?"},
            headers=headers,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["respuesta"] == "Perfecto, vamos."


@pytest.mark.asyncio
async def test_listar_conversaciones(api_client, db_session):
    user = Usuario(telegram_id=88002, nombre="Lista", telefono="+573008887766", email="l@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conv = Conversacion(
        usuario_id=user.id,
        titulo="Nutricion",
        canal_creador=CanalConversacion.ANDROID,
        activa=True,
    )
    db_session.add(conv)
    await db_session.commit()

    token = _sign_jwt(user.telegram_id)
    response = await api_client.get(
        "/api/me/conversaciones",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["conversaciones"]) >= 1
