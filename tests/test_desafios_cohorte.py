"""Tests cohorte y plantillas de desafíos."""
from datetime import date

from src.db.models import CategoriaDeporte, Usuario
from src.services.desafios.cohorte import cohorte_key_usuario, normalizar_nivel, normalizar_objetivo
from src.services.desafios.plantillas import calcular_meta, elegir_plantilla


def test_normalizar_nivel_principiante():
    assert normalizar_nivel("Principiante") == "principiante"
    assert normalizar_nivel(None) == "principiante"


def test_normalizar_objetivo_perder_grasa():
    assert normalizar_objetivo("quiero perder grasa") == "perder_grasa"
    assert normalizar_objetivo("mantenerme") == "mantener"


def test_cohorte_key_usuario():
    u = Usuario(
        telegram_id=1,
        categoria_deporte=CategoriaDeporte.URBANO,
        nivel="principiante",
        objetivo="perder grasa",
    )
    assert cohorte_key_usuario(u) == "urbano|principiante|perder_grasa"


def test_elegir_plantilla_deterministica():
    ck = "urbano|principiante|perder_grasa"
    p1 = elegir_plantilla(ck, date(2026, 5, 24))
    p2 = elegir_plantilla(ck, date(2026, 5, 24))
    assert p1.metrica == p2.metrica


def test_calcular_meta_streak_bonus():
    plantilla = elegir_plantilla("indoor_fuerza|principiante|general", date(2026, 1, 1))
    base = calcular_meta(plantilla, "principiante", streak_entreno=0)
    boosted = calcular_meta(plantilla, "principiante", streak_entreno=10)
    assert boosted >= base
