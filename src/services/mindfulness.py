"""Sesiones de mindfulness pre-grabadas con TTS cacheado."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.services.tts import generar_voz

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/entrenadorax_mindfulness")
CACHE_DIR.mkdir(exist_ok=True)


SESIONES = {
    "respiracion": {
        "titulo": "Respiracion 4-7-8 (3 min)",
        "texto": (
            "Inhala por la nariz 4 segundos. Mantiene 7 segundos. Exhala por la "
            "boca 8 segundos. Repite. Manten una postura comoda, sin tension en "
            "los hombros. Vamos. Inhala. Uno, dos, tres, cuatro. Manten. Uno, dos, "
            "tres, cuatro, cinco, seis, siete. Exhala. Uno, dos, tres, cuatro, "
            "cinco, seis, siete, ocho. Otra vez. Inhala. Manten. Exhala. "
            "Sigue tu propio ritmo. Cuando termines, abre los ojos suavemente."
        ),
    },
    "body_scan": {
        "titulo": "Body scan post-entreno (5 min)",
        "texto": (
            "Acuestate boca arriba. Cierra los ojos. Lleva la atencion a los "
            "pies. Sienteles. Soltalos. Sube a las pantorrillas. Sentilas pesadas. "
            "Relajalas. Cuadriceps. Gluteos. Lumbar. Abdomen. Pecho. Brazos. Manos. "
            "Cuello. Cara. Cabeza. Todo el cuerpo apoyado en el suelo. Respira "
            "profundo. Quedate aqui el tiempo que necesites."
        ),
    },
    "visualizacion": {
        "titulo": "Visualizacion pre-entreno (2 min)",
        "texto": (
            "Cierra los ojos. Visualiza tu primer ejercicio. Mirate haciendolo "
            "con perfecta tecnica. Siente la barra en tus manos. La tension en "
            "tus piernas. Eres fuerte. Eres consistente. Tu compromiso esta firme. "
            "Hoy entrenas porque dijiste que lo harias. Abre los ojos. Vamos."
        ),
    },
    "cool_down": {
        "titulo": "Cool-down (4 min)",
        "texto": (
            "Termino el entreno. Respira profundo. Una vez mas. Tu cuerpo te dio "
            "todo. Agradecelo. Recorre mentalmente las zonas trabajadas. "
            "Sientelas. Hidratate. Camina lentamente unos pasos. Tu sistema "
            "parasimpatico se activa. Cierra los ojos un momento. Quedate aqui."
        ),
    },
    "gratitud": {
        "titulo": "Gratitud (3 min)",
        "texto": (
            "Cierra los ojos. Piensa en tres cosas por las que estas agradecido "
            "hoy. Algo tuyo. Algo de alguien cercano. Algo del mundo. Sostenlas "
            "en tu mente sin juzgar. Tu cuerpo te permite entrenar. Eso es un "
            "regalo. Sigue respirando. Cuando estes listo, abre los ojos."
        ),
    },
}

VOZ_MINDFULNESS = "nova"


async def obtener_audio(slug: str) -> Optional[bytes]:
    """Devuelve audio (bytes opus) de la sesion. Genera con TTS y cachea."""
    sesion = SESIONES.get(slug)
    if sesion is None:
        return None
    cache_path = CACHE_DIR / f"{slug}.opus"
    if cache_path.exists():
        return cache_path.read_bytes()
    audio = await generar_voz(sesion["texto"], voice=VOZ_MINDFULNESS)
    if audio is None:
        return None
    data = audio.read()
    cache_path.write_bytes(data)
    return data


def listar_sesiones() -> list[dict]:
    return [{"slug": k, "titulo": v["titulo"]} for k, v in SESIONES.items()]
