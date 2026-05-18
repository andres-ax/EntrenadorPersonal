"""Tests del modulo jobs_deportes (PR3): registrar y validar callbacks."""
from unittest.mock import MagicMock

import pytest


def test_modulo_importable():
    """Smoke test: el modulo carga sin errores."""
    from src.telegram import jobs_deportes

    assert hasattr(jobs_deportes, "recordar_sesion_skill")
    assert hasattr(jobs_deportes, "peso_diario_camp")
    assert hasattr(jobs_deportes, "recovery_post_sparring")
    assert hasattr(jobs_deportes, "taper_alert")
    assert hasattr(jobs_deportes, "weekly_load_endurance")
    assert hasattr(jobs_deportes, "registrar_jobs_deportes")


def test_registrar_jobs_deportes_sin_jobqueue():
    """Si app.job_queue es None, no rompe (warning silent)."""
    from src.telegram.jobs_deportes import registrar_jobs_deportes

    app = MagicMock()
    app.job_queue = None
    registrar_jobs_deportes(app)


def test_registrar_jobs_deportes_registra_5_callbacks():
    """Con mock job_queue, registra los 5 jobs esperados."""
    from src.telegram.jobs_deportes import registrar_jobs_deportes

    app = MagicMock()
    registrar_jobs_deportes(app)
    names_registrados = {
        call.kwargs.get("name")
        for call in app.job_queue.run_daily.call_args_list
    }
    assert "recordar_sesion_skill" in names_registrados
    assert "peso_diario_camp" in names_registrados
    assert "recovery_post_sparring" in names_registrados
    assert "taper_alert" in names_registrados
    assert "weekly_load_endurance" in names_registrados


def test_categorias_validas_existen():
    from src.db.models import CategoriaDeporte

    assert CategoriaDeporte.URBANO.value == "urbano"
    assert CategoriaDeporte.COMBATE.value == "combate"
    assert CategoriaDeporte.OUTDOOR_ENDURANCE.value == "outdoor_endurance"


def test_subtipo_sesion_incluye_skill_sparring():
    from src.db.models import SubtipoSesion

    valores = {s.value for s in SubtipoSesion}
    assert "skill" in valores
    assert "sparring" in valores
    assert "drilling" in valores
    assert "competencia" in valores


def test_tipo_pr_incluye_truco_grado_tiempo():
    from src.db.models import TipoPR

    valores = {t.value for t in TipoPR}
    assert "peso_reps" in valores
    assert "truco" in valores
    assert "grado" in valores
    assert "tiempo" in valores
    assert "cinturon" in valores
    assert "profundidad" in valores


@pytest.mark.asyncio
async def test_recordar_sesion_skill_sin_usuarios():
    """Si no hay usuarios urbanos, no debe fallar."""
    from src.telegram import jobs_deportes

    ctx = MagicMock()
    ctx.bot = MagicMock()
    from unittest.mock import AsyncMock, patch

    with patch.object(
        jobs_deportes, "listar_usuarios_activos",
        new=AsyncMock(return_value=[]),
    ):
        await jobs_deportes.recordar_sesion_skill(ctx)
