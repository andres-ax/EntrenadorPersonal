"""Tests del nucleo run_coach_turn."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.db.models import CanalConversacion, Conversacion, RolMensajeChat, Usuario
from src.services.coach_turn import run_coach_turn


@pytest.mark.asyncio
async def test_run_coach_turn_persiste_mensajes(db_session):
    user = Usuario(telegram_id=99001, nombre="Test", telefono="+573001112233", email="t@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conv = Conversacion(
        usuario_id=user.id,
        titulo="Coach",
        canal_creador=CanalConversacion.TELEGRAM,
        es_principal=True,
        activa=True,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    mock_session = MagicMock()
    mock_session.close = AsyncMock()

    mock_result = MagicMock()
    mock_result.final_output = "Listo, registrado."
    mock_result.raw_responses = []

    with (
        patch("src.services.coach_turn.SafeRedisSession.from_url", return_value=mock_session),
        patch("src.services.coach_turn.Runner.run", AsyncMock(return_value=mock_result)),
        patch("src.services.coach_turn.build_coach_prompt", AsyncMock(return_value="prompt")),
        patch("src.services.coach_turn.grabar_auditoria_turno", AsyncMock()),
        patch(
            "src.services.coach_turn.aplicar_guardrails_output",
            return_value=("Listo, registrado.", []),
        ),
    ):
        result = await run_coach_turn(
            telegram_id=user.telegram_id,
            conversacion_id=conv.id,
            texto="Registra 80kg",
            canal="android",
            conversacion_titulo=conv.titulo,
        )

    assert result.respuesta == "Listo, registrado."
    assert result.mensaje_usuario_id is not None
    assert result.mensaje_coach_id is not None

    from src.db.models import MensajeChat
    from sqlalchemy import select

    msgs = (
        await db_session.execute(
            select(MensajeChat).where(MensajeChat.conversacion_id == conv.id)
        )
    ).scalars().all()
    assert len(msgs) == 2
    assert msgs[0].rol == RolMensajeChat.USER
    assert msgs[1].rol == RolMensajeChat.ASSISTANT
