"""Internacionalizacion ligera: lookup en JSON + interpolacion + jerga regional.

Uso:
    from src.i18n import t, plural, detectar_idioma, aplicar_jerga

    t("saludo_inicial", lang="es", nombre="Andres")          # "Hola Andres, listo para entrenar?"
    plural("dias_sin_entrenar", count=3, lang="es")          # "3 dias sin entrenar"
    aplicar_jerga("amigo, vamos!", pais="CO")                # "parce, vamos!"
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

I18N_DIR = Path(__file__).parent
IDIOMA_DEFAULT = "es"
IDIOMAS_SOPORTADOS = ("es", "en", "pt")

# Mapping language_code Telegram (BCP-47) a nuestros codigos cortos.
# Telegram envia ej: "es", "es-CO", "en-US", "pt-BR".
TELEGRAM_LANG_MAP = {
    "es": "es",
    "es-co": "es",
    "es-mx": "es",
    "es-ar": "es",
    "es-cl": "es",
    "es-pe": "es",
    "es-ec": "es",
    "es-uy": "es",
    "es-bo": "es",
    "es-py": "es",
    "es-cr": "es",
    "es-do": "es",
    "es-pa": "es",
    "es-ve": "es",
    "es-419": "es",
    "es-es": "es",
    "en": "en",
    "en-us": "en",
    "en-gb": "en",
    "en-au": "en",
    "en-ca": "en",
    "pt": "pt",
    "pt-br": "pt",
    "pt-pt": "pt",
}

# Jerga regional: reemplaza terminos genericos por jerga local.
# Aplicar a copies tono "amigable" y "firme" (NO militar para mantener seriedad).
JERGA_REGIONAL = {
    "CO": {
        " amigo": " parce",
        " amiga": " parcera",
        "Amigo,": "Parce,",
        "Amiga,": "Parcera,",
        " hermano": " parce",
        " loco": " marica",
        "vacano": "chevere",
        "Que mas": "Que mas pues",
        "increible": "una nota",
    },
    "MX": {
        " amigo": " guey",
        " amiga": " guey",
        "Amigo,": "Guey,",
        " hermano": " carnal",
        "increible": "chido",
        "Genial": "Padre",
        "Que mas": "Que onda",
    },
    "AR": {
        " amigo": " che",
        "Amigo,": "Che,",
        " hermano": " loco",
        "increible": "una masa",
        "Genial": "Buenisimo",
        "Que mas": "Que onda",
    },
    "ES": {
        " amigo": " tio",
        "Amigo,": "Tio,",
        "increible": "brutal",
    },
    "PE": {
        " amigo": " causa",
        "Amigo,": "Causa,",
        "increible": "bacan",
    },
    "CL": {
        " amigo": " weon",
        "Amigo,": "Weon,",
        "increible": "la raja",
    },
}


@lru_cache(maxsize=8)
def _cargar(lang: str) -> dict:
    if lang not in IDIOMAS_SOPORTADOS:
        lang = IDIOMA_DEFAULT
    f = I18N_DIR / f"{lang}.json"
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Error leyendo i18n %s", lang)
        return {}


def detectar_idioma(telegram_lang_code: str | None) -> str:
    """Mapea BCP-47 de Telegram a uno de nuestros 3 idiomas soportados."""
    if not telegram_lang_code:
        return IDIOMA_DEFAULT
    code = telegram_lang_code.lower().strip()
    if code in TELEGRAM_LANG_MAP:
        return TELEGRAM_LANG_MAP[code]
    base = code.split("-")[0]
    if base in IDIOMAS_SOPORTADOS:
        return base
    return IDIOMA_DEFAULT


def aplicar_jerga(texto: str, pais: str | None) -> str:
    """Aplica jerga regional al texto. NoOp si pais no esta en la tabla."""
    if not texto or not pais:
        return texto
    reglas = JERGA_REGIONAL.get(pais.upper())
    if not reglas:
        return texto
    resultado = texto
    for k, v in reglas.items():
        resultado = resultado.replace(k, v)
    return resultado


def t(key: str, lang: str = IDIOMA_DEFAULT, pais: str | None = None, **kwargs) -> str:
    """Traduce una key. Si no existe usa la key como fallback.

    Si `pais` se pasa, aplica jerga regional al resultado.
    """
    if not lang:
        lang = IDIOMA_DEFAULT
    data = _cargar(lang)
    valor = data.get(key)
    if valor is None and lang != IDIOMA_DEFAULT:
        valor = _cargar(IDIOMA_DEFAULT).get(key, key)
    if valor is None:
        valor = key
    try:
        resultado = valor.format(**kwargs)
    except (KeyError, IndexError):
        resultado = valor
    if pais:
        resultado = aplicar_jerga(resultado, pais)
    return resultado


def plural(
    key: str, count: int, lang: str = IDIOMA_DEFAULT, pais: str | None = None, **kwargs
) -> str:
    """Selecciona forma plural segun CLDR simplificado.

    Reglas:
    - es/en/pt: one cuando count == 1, other para el resto (incluye 0).
    - Espera keys: `<key>.one` y `<key>.other`.
    """
    sub = "one" if count == 1 else "other"
    return t(f"{key}.{sub}", lang, pais=pais, count=count, **kwargs)
