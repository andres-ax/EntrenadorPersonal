"""Integración escalación: digest único, timezone."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.db.models import Usuario, TonoCoach
from src.telegram import escalation as esc


@pytest.mark.asyncio
async def test_construir_digest_pendientes(monkeypatch):
    u = Usuario(
        id=1,
        telegram_id=111,
        nombre="Test",
        tono=TonoCoach.FIRME,
        timezone="America/Bogota",
    )

    async def fake_cumplio(_uid, tipo, **kw):
        return tipo == "entreno"

    monkeypatch.setattr(esc, "_ya_cumplio_hoy", fake_cumplio)
    texto = await esc._construir_digest(u)
    assert texto is not None
    assert "Comida" in texto
    assert "Sueno" in texto
    assert "Entreno" not in texto


@pytest.mark.asyncio
async def test_usuario_inactivo_no_escala(monkeypatch):
    u = Usuario(id=1, telegram_id=111, timezone="America/Bogota")

    monkeypatch.setattr(esc, "count_auditoria_reciente", AsyncMock(return_value=0))
    assert await esc._usuario_debe_escalarse(u) is False

    monkeypatch.setattr(esc, "count_auditoria_reciente", AsyncMock(return_value=5))
    monkeypatch.setattr(
        esc, "_dias_consecutivos_sin", AsyncMock(return_value=45)
    )
    assert await esc._tipo_debe_escalarse(u, "entreno") is False
