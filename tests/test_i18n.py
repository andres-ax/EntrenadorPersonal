"""Tests del modulo i18n: traduccion, pluralizacion, jerga regional, deteccion idioma."""

from __future__ import annotations

from src.i18n import IDIOMAS_SOPORTADOS, aplicar_jerga, detectar_idioma, plural, t


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


def test_t_en_y_pt():
    es = t("saludo_inicial", "es", nombre="A")
    en = t("saludo_inicial", "en", nombre="A")
    pt = t("saludo_inicial", "pt", nombre="A")
    assert es != en
    assert es != pt
    assert en != pt
    assert "A" in es and "A" in en and "A" in pt


def test_plural():
    assert "1 dia" in plural("dias_sin_entrenar", 1, "es")
    assert "5 dias" in plural("dias_sin_entrenar", 5, "es")
    assert "1 day" in plural("dias_sin_entrenar", 1, "en")
    assert "5 days" in plural("dias_sin_entrenar", 5, "en")
    assert "1 dia" in plural("dias_sin_entrenar", 1, "pt")


def test_plural_count_cero():
    assert "0 days" in plural("dias_sin_entrenar", 0, "en")
    assert "0 dias" in plural("dias_sin_entrenar", 0, "es")


def test_detectar_idioma_telegram_codes():
    assert detectar_idioma("es-CO") == "es"
    assert detectar_idioma("es-MX") == "es"
    assert detectar_idioma("ES-AR") == "es"
    assert detectar_idioma("en-US") == "en"
    assert detectar_idioma("en-GB") == "en"
    assert detectar_idioma("pt-BR") == "pt"
    assert detectar_idioma("pt-PT") == "pt"


def test_detectar_idioma_base():
    assert detectar_idioma("es") == "es"
    assert detectar_idioma("en") == "en"
    assert detectar_idioma("pt") == "pt"


def test_detectar_idioma_desconocido():
    assert detectar_idioma("fr") == "es"
    assert detectar_idioma("zh-CN") == "es"
    assert detectar_idioma("") == "es"
    assert detectar_idioma(None) == "es"


def test_jerga_colombia():
    res = aplicar_jerga("Hola amigo, vamos", "CO")
    assert "parce" in res


def test_jerga_mexico():
    res = aplicar_jerga("Hola amigo, increible esto", "MX")
    assert "guey" in res or "chido" in res


def test_jerga_argentina():
    res = aplicar_jerga("Hola amigo, increible esto", "AR")
    assert "che" in res or "masa" in res


def test_jerga_pais_invalido_noop():
    assert aplicar_jerga("Hola amigo", "XX") == "Hola amigo"
    assert aplicar_jerga("Hola amigo", None) == "Hola amigo"


def test_t_con_pais_aplica_jerga():
    res = t("saludo_inicial", "es", pais="CO", nombre="Andres")
    assert "Andres" in res


def test_keys_consistentes_entre_idiomas():
    """Las keys principales deben existir en los 3 idiomas."""
    keys_obligatorias = [
        "saludo_inicial",
        "boton_pagar",
        "cmd_start",
        "cmd_pagar",
        "bot_descripcion",
        "bot_short_desc",
    ]
    for k in keys_obligatorias:
        for lang in IDIOMAS_SOPORTADOS:
            valor = t(k, lang)
            assert valor != k, f"Key {k} falta en {lang}.json"
            assert len(valor) > 0
