"""Plantillas determinísticas de desafíos diarios."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class PlantillaDesafio:
    metrica: str
    titulo: str
    descripcion: str
    meta_principiante: float
    meta_intermedio: float
    meta_avanzado: float
    categorias: tuple[str, ...] = ()
    objetivos: tuple[str, ...] = ()


PLANTILLAS: tuple[PlantillaDesafio, ...] = (
    PlantillaDesafio(
        metrica="minutos_entreno",
        titulo="Movimiento del día",
        descripcion="Acumula minutos de entrenamiento (skate, casa, gym o deporte).",
        meta_principiante=25,
        meta_intermedio=40,
        meta_avanzado=55,
        categorias=("urbano", "outdoor_endurance", "combate", "escalada"),
    ),
    PlantillaDesafio(
        metrica="sesiones",
        titulo="Sesión completada",
        descripcion="Registra al menos una sesión de entrenamiento hoy.",
        meta_principiante=1,
        meta_intermedio=1,
        meta_avanzado=2,
        categorias=("indoor_fuerza", "equipo", "otro"),
    ),
    PlantillaDesafio(
        metrica="volumen_kg",
        titulo="Volumen de fuerza",
        descripcion="Suma volumen (kg × series × reps) en tus ejercicios del día.",
        meta_principiante=4000,
        meta_intermedio=8000,
        meta_avanzado=12000,
        categorias=("indoor_fuerza",),
        objetivos=("ganar_musculo", "rendimiento"),
    ),
    PlantillaDesafio(
        metrica="comidas",
        titulo="Registro consciente",
        descripcion="Registra tus comidas del día para mantener adherencia nutricional.",
        meta_principiante=3,
        meta_intermedio=3,
        meta_avanzado=4,
        objetivos=("perder_grasa", "mantener", "general"),
    ),
    PlantillaDesafio(
        metrica="agua_ml",
        titulo="Hidratación base",
        descripcion="Alcanza el 80% de tu objetivo de agua del día.",
        meta_principiante=0.8,
        meta_intermedio=0.85,
        meta_avanzado=0.9,
    ),
)

DEFAULT_PREMIO = {"top1": "freeze", "top3": "badge"}


def _meta_por_nivel(plantilla: PlantillaDesafio, nivel: str) -> float:
    if nivel == "avanzado":
        return plantilla.meta_avanzado
    if nivel == "intermedio":
        return plantilla.meta_intermedio
    return plantilla.meta_principiante


def elegir_plantilla(cohorte_key: str, fecha: date) -> PlantillaDesafio:
    parts = cohorte_key.split("|")
    cat = parts[0] if parts else "otro"
    obj = parts[2] if len(parts) > 2 else "general"
    candidatas = [
        p
        for p in PLANTILLAS
        if (not p.categorias or cat in p.categorias)
        and (not p.objetivos or obj in p.objetivos)
    ]
    if not candidatas:
        candidatas = list(PLANTILLAS)
    idx = fecha.toordinal() % len(candidatas)
    return candidatas[idx]


def calcular_meta(
    plantilla: PlantillaDesafio,
    nivel: str,
    *,
    streak_entreno: int = 0,
    sesiones_ultimos_7: int = 0,
) -> float:
    meta = _meta_por_nivel(plantilla, nivel)
    if streak_entreno >= 7:
        meta *= 1.1
    if nivel == "principiante" and sesiones_ultimos_7 == 0:
        meta *= 0.85
    if plantilla.metrica in ("sesiones", "comidas"):
        return max(1, round(meta))
    if plantilla.metrica == "agua_ml":
        return round(meta, 2)
    return round(meta, 1)
