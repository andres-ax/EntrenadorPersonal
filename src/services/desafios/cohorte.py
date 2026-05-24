"""Derivacion de cohorte desde perfil de usuario."""
from __future__ import annotations

import re

from src.db.models import CategoriaDeporte, Usuario

_NIVEL_MAP = {
    "principiante": "principiante",
    "beginner": "principiante",
    "novato": "principiante",
    "intermedio": "intermedio",
    "intermediate": "intermedio",
    "medio": "intermedio",
    "avanzado": "avanzado",
    "advanced": "avanzado",
    "experto": "avanzado",
    "pro": "avanzado",
}

_OBJETIVO_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"perder|bajar|grasa|definir|adelgaz", re.I), "perder_grasa"),
    (re.compile(r"ganar|muscul|hipertro|volumen|masa", re.I), "ganar_musculo"),
    (re.compile(r"rendim|compet|performance|pr\b|record", re.I), "rendimiento"),
    (re.compile(r"manten|salud|forma", re.I), "mantener"),
]


def normalizar_nivel(raw: str | None) -> str:
    if not raw:
        return "principiante"
    key = raw.strip().lower()
    return _NIVEL_MAP.get(key, "intermedio")


def normalizar_objetivo(raw: str | None) -> str:
    if not raw:
        return "general"
    text = raw.strip()
    for pattern, label in _OBJETIVO_PATTERNS:
        if pattern.search(text):
            return label
    return "general"


def cohorte_key_usuario(usuario: Usuario) -> str:
    cat = usuario.categoria_deporte
    if cat is None:
        cat_str = CategoriaDeporte.OTRO.value
    elif isinstance(cat, CategoriaDeporte):
        cat_str = cat.value
    else:
        cat_str = str(cat)
    nivel = normalizar_nivel(usuario.nivel)
    objetivo = normalizar_objetivo(usuario.objetivo)
    return f"{cat_str}|{nivel}|{objetivo}"


def cohorte_label(cohorte_key: str) -> str:
    parts = cohorte_key.split("|")
    if len(parts) != 3:
        return cohorte_key
    cat, nivel, obj = parts
    return f"{cat.replace('_', ' ')} · {nivel} · {obj.replace('_', ' ')}"
