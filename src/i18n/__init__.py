"""Internacionalizacion ligera: lookup en JSON + interpolacion."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

I18N_DIR = Path(__file__).parent
IDIOMA_DEFAULT = "es"
IDIOMAS_SOPORTADOS = ("es", "en", "pt")


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


def t(key: str, lang: str = IDIOMA_DEFAULT, **kwargs) -> str:
    """Traduce una key. Si no existe usa la key como fallback."""
    if not lang:
        lang = IDIOMA_DEFAULT
    data = _cargar(lang)
    valor = data.get(key)
    if valor is None and lang != IDIOMA_DEFAULT:
        valor = _cargar(IDIOMA_DEFAULT).get(key, key)
    if valor is None:
        valor = key
    try:
        return valor.format(**kwargs)
    except (KeyError, IndexError):
        return valor


def plural(key: str, count: int, lang: str = IDIOMA_DEFAULT, **kwargs) -> str:
    """Selecciona one/other segun count. Espera keys: '<key>.one' y '<key>.other'."""
    sub = "one" if count == 1 else "other"
    return t(f"{key}.{sub}", lang, count=count, **kwargs)
