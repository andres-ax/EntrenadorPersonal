"""Tests modo libre vs onboarding en prompt del coach."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.db.models import CanalConversacion, Conversacion, Usuario
from src.services.coach_context import build_coach_prompt
from src.services.coach_modo import resolver_modo_coach


@pytest.mark.asyncio
async def test_modo_libre_hilo_android(db_session):
    user = Usuario(
        telegram_id=99100,
        nombre="Libre",
        telefono="+573009991100",
        email="libre@test.com",
        onboarding_completo=False,
    )
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
    await db_session.refresh(conv)

    modo = await resolver_modo_coach(user.telegram_id, conv.id, "android")
    assert modo == "libre"


@pytest.mark.asyncio
async def test_modo_onboarding_hilo_principal_tg(db_session):
    user = Usuario(
        telegram_id=99101,
        nombre="Onb",
        telefono="+573009991101",
        email="onb@test.com",
        onboarding_completo=False,
    )
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

    modo = await resolver_modo_coach(user.telegram_id, conv.id, "telegram")
    assert modo == "onboarding_telegram"


@pytest.mark.asyncio
async def test_prompt_incluye_modo_libre(db_session):
    user = Usuario(
        telegram_id=99102,
        nombre="Prompt",
        telefono="+573009991102",
        email="prompt@test.com",
        onboarding_completo=True,
        peso_kg=75.0,
        objetivo="ganar musculo",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    conv = Conversacion(
        usuario_id=user.id,
        titulo="App",
        canal_creador=CanalConversacion.ANDROID,
        activa=True,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)

    with patch(
        "src.services.coach_historial_snapshot.build_historial_snapshot",
        AsyncMock(return_value="Entrenos 7d: sin registros"),
    ):
        prompt = await build_coach_prompt(
            "Como voy?",
            user.telegram_id,
            conversacion_id=conv.id,
            canal="android",
        )
    assert "modo=libre" in prompt
    assert "historial_deportista=" in prompt
    assert "modo=onboarding_telegram" not in prompt
