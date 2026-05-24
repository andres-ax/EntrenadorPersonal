"""Tests métrica/evento mapping."""
from src.services.desafios.scoring import METRICA_EVENTO


def test_metrica_evento_keys():
    assert METRICA_EVENTO["comidas"] == "comidas"
    assert METRICA_EVENTO["minutos_entreno"] == "minutos_entreno"
    assert "agua_ml" in METRICA_EVENTO
