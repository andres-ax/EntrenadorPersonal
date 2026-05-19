"""Tests de las plantillas de escalation."""

import pytest

from src.telegram.escalation import (ESCALADO_COPY, MAX_LEVEL,
                                     MAX_MENSAJES_DIA, OFFSET_POR_LEVEL,
                                     _formatear_copy)


def test_escalado_copy_completo():
    """Verifica cobertura: 4 tipos x 3 tonos x 5 niveles."""
    tipos = ["entreno", "comida", "sueno", "peso"]
    tonos = ["amigable", "firme", "militar"]
    for tipo in tipos:
        assert tipo in ESCALADO_COPY
        for tono in tonos:
            assert tono in ESCALADO_COPY[tipo], f"falta {tipo}/{tono}"
            assert len(ESCALADO_COPY[tipo][tono]) >= MAX_LEVEL + 1


@pytest.mark.parametrize("tipo", ["entreno", "comida", "sueno", "peso"])
@pytest.mark.parametrize("tono", ["amigable", "firme", "militar"])
def test_formato_copy_no_revienta(tipo, tono):
    for level in range(0, MAX_LEVEL + 1):
        texto = _formatear_copy(
            nombre="Test",
            tono=tono,
            tipo_accion=tipo,
            level=level,
            dias=3,
            streak=10,
            objetivo="perder grasa",
            freq=4,
        )
        assert isinstance(texto, str)


def test_offsets_levels():
    assert 1 in OFFSET_POR_LEVEL and 2 in OFFSET_POR_LEVEL and 3 in OFFSET_POR_LEVEL
    assert OFFSET_POR_LEVEL[1] >= OFFSET_POR_LEVEL[3]


def test_max_mensajes_dia_razonable():
    assert 1 <= MAX_MENSAJES_DIA <= 6
