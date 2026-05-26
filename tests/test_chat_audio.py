"""Tests endpoint audio chat (Whisper)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.api.auth import _sign_jwt
from src.db.models import CanalConversacion, Conversacion, Usuario
from src.services.coach_turn import CoachTurnResult


@pytest.mark.asyncio
async def test_chat_audio_transcribe_y_responde(api_client, db_session):
    user = Usuario(telegram_id=66001, nombre="Voz", telefono="+573006665544", email="v@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conv = Conversacion(
        usuario_id=user.id,
        titulo="Voz",
        canal_creador=CanalConversacion.ANDROID,
        activa=True,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    token = _sign_jwt(user.telegram_id)
    headers = {"Authorization": f"Bearer {token}"}

    mock_result = CoachTurnResult(
        respuesta="Registrado tu entreno.",
        mensaje_usuario_id=10,
        mensaje_coach_id=11,
    )

    with (
        patch("src.api.chat.transcribir_audio", AsyncMock(return_value="Hice pierna hoy")),
        patch("src.api.chat.run_coach_turn", AsyncMock(return_value=mock_result)),
        patch("src.api.chat.check_rate_limit", AsyncMock(return_value=True)),
        patch("src.api.chat.check_daily_quota", AsyncMock(return_value=(True, 1, 25))),
    ):
        response = await api_client.post(
            f"/api/me/conversaciones/{conv.id}/audio",
            headers=headers,
            files={"file": ("voice.m4a", b"fake-audio-bytes", "audio/mp4")},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["transcripcion"] == "Hice pierna hoy"
    assert data["respuesta"] == "Registrado tu entreno."
