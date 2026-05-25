"""Tests de tools de deportes combate (PR3): sparring, pelea, cut, screening concusion."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import call_tool


def _ok(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, raw
    return d


def _err(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is False, raw
    return d


@pytest.mark.asyncio
async def test_calcular_cut_dentro_categoria():
    from src.tools import calcular_peso_objetivo_responsable

    with patch("src.tools.log_evento", new=AsyncMock()):
        raw = await call_tool(
            calcular_peso_objetivo_responsable,
            telegram_id=1,
            peso_actual_kg=68.0,
            peso_categoria_kg=70.0,
            dias_hasta_pesaje=30,
            estilo_combate="mma",
        )
    data = _ok(raw)
    assert "ya estas en categoria" in data["plan"]


@pytest.mark.asyncio
async def test_calcular_cut_responsable_normal():
    from src.tools import calcular_peso_objetivo_responsable

    with patch("src.tools.log_evento", new=AsyncMock()):
        raw = await call_tool(
            calcular_peso_objetivo_responsable,
            telegram_id=1,
            peso_actual_kg=73.0,
            peso_categoria_kg=70.0,
            dias_hasta_pesaje=60,
            estilo_combate="boxeo",
        )
    data = _ok(raw)
    assert data["delta_pct"] < 5
    assert "fase_cronica" in data
    assert "Reale" in data["cita_principal"]


@pytest.mark.asyncio
async def test_calcular_cut_critico_8pct_2sem():
    from src.tools import calcular_peso_objetivo_responsable

    with patch("src.tools.log_evento", new=AsyncMock()):
        raw = await call_tool(
            calcular_peso_objetivo_responsable,
            telegram_id=1,
            peso_actual_kg=80.0,
            peso_categoria_kg=70.0,
            dias_hasta_pesaje=10,
            estilo_combate="mma",
        )
    data = _ok(raw)
    assert data.get("alerta_critica") is True


@pytest.mark.asyncio
async def test_calcular_cut_agudo_excesivo():
    from src.tools import calcular_peso_objetivo_responsable

    with patch("src.tools.log_evento", new=AsyncMock()):
        raw = await call_tool(
            calcular_peso_objetivo_responsable,
            telegram_id=1,
            peso_actual_kg=78.0,
            peso_categoria_kg=70.0,
            dias_hasta_pesaje=3,
            estilo_combate="boxeo",
        )
    data = _ok(raw)
    assert data.get("alerta_critica") is True


@pytest.mark.asyncio
async def test_registrar_sparring_estilo_invalido():
    from src.tools import registrar_sparring

    raw = await call_tool(
        registrar_sparring,
        telegram_id=1,
        estilo="tenis",
        rounds=3,
    )
    _err(raw)


@pytest.mark.asyncio
async def test_registrar_sparring_carga_alta_alerta():
    """8 rounds x 15 min = 120 min > 90 min activa alerta."""
    from src.tools import registrar_sparring

    sesion_mock = type("S", (), {"id": 99})()
    with patch(
        "src.tools.repo_guardar_sesion_sparring",
        new=AsyncMock(return_value=sesion_mock),
    ):
        with patch("src.tools.incrementar_streak", new=AsyncMock()):
            with patch("src.tools.log_evento", new=AsyncMock()):
                raw = await call_tool(
                    registrar_sparring,
                    telegram_id=1,
                    estilo="mma",
                    rounds=8,
                    duracion_round_min=15,
                    intensidad_1_10=7,
                )
    data = _ok(raw)
    assert data["alerta_carga_alta"] is True


@pytest.mark.asyncio
async def test_registrar_sparring_golpe_cabeza_flag():
    from src.tools import registrar_sparring

    sesion_mock = type("S", (), {"id": 100})()
    with patch(
        "src.tools.repo_guardar_sesion_sparring",
        new=AsyncMock(return_value=sesion_mock),
    ):
        with patch("src.tools.incrementar_streak", new=AsyncMock()):
            with patch("src.tools.log_evento", new=AsyncMock()):
                raw = await call_tool(
                    registrar_sparring,
                    telegram_id=1,
                    estilo="boxeo",
                    rounds=4,
                    duracion_round_min=3,
                    intensidad_1_10=8,
                    golpe_cabeza_fuerte=True,
                )
    data = _ok(raw)
    assert data["alerta_concusion"] is True


@pytest.mark.asyncio
async def test_registrar_pelea_rebound_alto():
    """Pesaje 70kg, dia pelea 80kg = 14.3% rebound activa alerta."""
    from src.tools import registrar_pelea

    with patch("src.tools.log_evento", new=AsyncMock()):
        raw = await call_tool(
            registrar_pelea,
            telegram_id=1,
            estilo="mma",
            resultado="ganada",
            metodo="decision_unanime",
            peso_pesaje_kg=70.0,
            peso_dia_pelea_kg=80.0,
            round_final=0,
        )
    data = _ok(raw)
    assert data["alerta_rebound_alto"] is True
    assert data["rebound_pct"] > 10


@pytest.mark.asyncio
async def test_evaluar_concusion_minima():
    from src.tools import evaluar_concusion_simplificado

    with patch("src.tools.log_evento", new=AsyncMock()):
        raw = await call_tool(evaluar_concusion_simplificado, telegram_id=1)
    data = _ok(raw)
    assert data["severidad"] == "minima"
    assert data["off_sport_dias"] == 1


@pytest.mark.asyncio
async def test_evaluar_concusion_alta_perdida_consciencia():
    from src.tools import evaluar_concusion_simplificado

    with patch("src.tools.log_evento", new=AsyncMock()):
        raw = await call_tool(
            evaluar_concusion_simplificado,
            telegram_id=1,
            tuvo_perdida_conciencia=True,
            duracion_perdida_seg=45,
        )
    data = _ok(raw)
    assert data["severidad"] == "alta"
    assert data["off_sport_dias"] == 21
    assert "URGENCIAS" in data["recomendacion"] or "urgencias" in data["recomendacion"].lower()


@pytest.mark.asyncio
async def test_evaluar_concusion_moderada_multi_sintomas():
    from src.tools import evaluar_concusion_simplificado

    with patch("src.tools.log_evento", new=AsyncMock()):
        raw = await call_tool(
            evaluar_concusion_simplificado,
            telegram_id=1,
            nausea_vomito=True,
            mareo_persistente=True,
            confusion_amnesia=True,
        )
    data = _ok(raw)
    assert data["severidad"] == "moderada"
    assert data["off_sport_dias"] == 14
