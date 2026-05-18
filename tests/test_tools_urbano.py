"""Tests de tools de deportes urbanos (PR3): truco, sesion_skill, via, progreso."""
import json
from unittest.mock import AsyncMock, patch

import pytest

from src.tools import DEPORTES_URBANO_TRICKS
from tests.conftest import call_tool


def _ok(raw: str) -> dict:
    data = json.loads(raw)
    assert data.get("ok") is True, raw
    return data


def _err(raw: str) -> dict:
    data = json.loads(raw)
    assert data.get("ok") is False, raw
    return data


def test_deportes_urbano_set_correcto():
    assert "skate" in DEPORTES_URBANO_TRICKS
    assert "bmx" in DEPORTES_URBANO_TRICKS
    assert "rollers" in DEPORTES_URBANO_TRICKS
    assert "parkour" in DEPORTES_URBANO_TRICKS
    assert "gimnasio" not in DEPORTES_URBANO_TRICKS


@pytest.mark.asyncio
async def test_registrar_truco_aterrizado_deporte_invalido():
    from src.tools import registrar_truco_aterrizado

    raw = await call_tool(
        registrar_truco_aterrizado,
        telegram_id=1, deporte="gimnasio", nombre_truco="kickflip",
    )
    data = _err(raw)
    assert "deporte invalido" in data["error"]


@pytest.mark.asyncio
async def test_registrar_truco_aterrizado_nombre_vacio():
    from src.tools import registrar_truco_aterrizado

    raw = await call_tool(
        registrar_truco_aterrizado,
        telegram_id=1, deporte="skate", nombre_truco="",
    )
    _err(raw)


@pytest.mark.asyncio
async def test_registrar_sesion_skill_duracion_invalida():
    from src.tools import registrar_sesion_skill

    raw = await call_tool(
        registrar_sesion_skill,
        telegram_id=1, deporte="bmx", duracion_min=1000,
    )
    _err(raw)


@pytest.mark.asyncio
async def test_registrar_sesion_skill_sensacion_fuera_rango():
    from src.tools import registrar_sesion_skill

    raw = await call_tool(
        registrar_sesion_skill,
        telegram_id=1, deporte="skate", duracion_min=60, sensacion_1_5=10,
    )
    _err(raw)


@pytest.mark.asyncio
async def test_registrar_via_escalada_grado_invalido():
    from src.tools import registrar_via_escalada

    raw = await call_tool(
        registrar_via_escalada,
        telegram_id=1, nombre_via="El Lobo", grado="muy dificil", spot="Suesca",
    )
    _err(raw)


@pytest.mark.asyncio
async def test_registrar_via_escalada_estilo_invalido():
    from src.tools import registrar_via_escalada

    raw = await call_tool(
        registrar_via_escalada,
        telegram_id=1, nombre_via="X", grado="5.10a",
        spot="Suesca", estilo="xyz",
    )
    _err(raw)


@pytest.mark.asyncio
async def test_consultar_progreso_skill_ventana_invalida():
    from src.tools import consultar_progreso_skill

    raw = await call_tool(
        consultar_progreso_skill,
        telegram_id=1, deporte="skate", ventana_dias=5,
    )
    _err(raw)


@pytest.mark.asyncio
async def test_registrar_via_escalada_grado_yds_valido():
    from src.tools import registrar_via_escalada

    with patch(
        "src.tools.repo_guardar_pr_via",
        new=AsyncMock(return_value=type("PR", (), {"id": 123})()),
    ):
        with patch("src.tools.log_evento", new=AsyncMock()):
            raw = await call_tool(
                registrar_via_escalada,
                telegram_id=1, nombre_via="Pino", grado="5.10a",
                spot="Suesca", estilo="onsight",
            )
    data = _ok(raw)
    assert data["grado"] == "5.10a"
    assert data["estilo"] == "on_sight"


@pytest.mark.asyncio
async def test_registrar_via_escalada_grado_font_valido():
    from src.tools import registrar_via_escalada

    with patch(
        "src.tools.repo_guardar_pr_via",
        new=AsyncMock(return_value=type("PR", (), {"id": 124})()),
    ):
        with patch("src.tools.log_evento", new=AsyncMock()):
            raw = await call_tool(
                registrar_via_escalada,
                telegram_id=1, nombre_via="Boulder X",
                grado="V6", spot="Macheta",
            )
    data = _ok(raw)
    assert data["grado"] == "V6"


@pytest.mark.asyncio
async def test_registrar_via_escalada_alerta_dedos():
    from src.tools import registrar_via_escalada

    with patch(
        "src.tools.repo_guardar_pr_via",
        new=AsyncMock(return_value=type("PR", (), {"id": 125})()),
    ):
        with patch("src.tools.log_evento", new=AsyncMock()):
            raw = await call_tool(
                registrar_via_escalada,
                telegram_id=1, nombre_via="X", grado="5.11a",
                spot="Suesca", lesion_dedo_si_no=True,
            )
    data = _ok(raw)
    assert data["alerta_dedos"] is True
