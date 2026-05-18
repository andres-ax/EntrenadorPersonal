"""Tests del modulo i18n."""
from __future__ import annotations

from src.i18n import IDIOMAS_SOPORTADOS, plural, t


def test_idiomas_soportados():
    assert "es" in IDIOMAS_SOPORTADOS
    assert "en" in IDIOMAS_SOPORTADOS
    assert "pt" in IDIOMAS_SOPORTADOS


def test_t_interpolacion():
    s = t("saludo_inicial", "es", nombre="Andres")
    assert "Andres" in s


def test_t_fallback_lang():
    assert t("saludo_inicial", "xx", nombre="X") == t("saludo_inicial", "es", nombre="X")


def test_t_fallback_key():
    assert t("key_que_no_existe", "es") == "key_que_no_existe"


def test_plural():
    assert "1 dia" in plural("dias_sin_entrenar", 1, "es")
    assert "5 dias" in plural("dias_sin_entrenar", 5, "es")
    assert "1 day" in plural("dias_sin_entrenar", 1, "en")
    assert "5 days" in plural("dias_sin_entrenar", 5, "en")
