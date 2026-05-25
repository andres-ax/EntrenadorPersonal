"""OpenAI Vision para analisis de fotos de comida.

Devuelve estimacion de alimentos, calorias, macros y un feedback corto.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from io import BytesIO

from openai import AsyncOpenAI

from src.config import settings
from src.db.repository import log_llm_usage

logger = logging.getLogger(__name__)

# Timeout explicito para Vision: una llamada tipica responde en 3-7s; 25s
# da margen razonable y evita esperas de 30+s (vimos 36s en prod). max_retries=1
# para que un fallo transitorio no bloquee al usuario, sin acumular costo.
_VISION_TIMEOUT_S = 25.0
_VISION_MAX_RETRIES = 1

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=_VISION_TIMEOUT_S,
            max_retries=_VISION_MAX_RETRIES,
        )
    return _client


def _prompt_sistema(tono: str) -> str:
    base = (
        "Eres un nutricionista deportivo ISSN-CISSN. Analiza la foto que "
        "envia el usuario. Puede ser:\n"
        "1) Un plato/comida lista para comer (caso normal): identifica "
        "   alimentos y estima calorias y macros.\n"
        "2) Una etiqueta nutricional o paquete de producto: extrae los "
        "   valores de la etiqueta tal cual aparecen (por porcion).\n"
        "3) Un alimento crudo, ingrediente o pieza de fruta/verdura: "
        "   estima como porcion estandar.\n"
        "4) Bebidas, infusiones, suplementos (proteina, creatina) o liquidos: "
        "   identificalos y estima su aporte nutricional.\n\n"
        "Devuelve SOLO JSON valido con esta forma:\n"
        '{"alimentos": ["alimento1","alimento2",...], "calorias": int, '
        '"proteinas_g": float, "carbohidratos_g": float, "grasas_g": float, '
        '"fuente": "estimacion" | "etiqueta" | "ingrediente_crudo", '
        '"feedback": "1-2 frases sobre el impacto en su objetivo"}\n\n'
        "Si la foto NO contiene comida, bebidas, suplementos, ingredientes, ni etiqueta "
        "nutricional (ej: foto de skate, perro, paisaje, captura de "
        "pantalla sin info nutricional), devuelve "
        '{"error": "no_food"}.\n'
        "Nunca uses lenguaje alimento limpio/sucio ni hagas shaming. "
        "Nunca des diagnostico medico."
    )
    if tono == "militar":
        base += " Tono: directo, imperativo, sin rodeos."
    elif tono == "firme":
        base += " Tono: directo y motivacional."
    else:
        base += " Tono: empatico y constructivo."
    return base


async def analizar_comida(
    foto_bytes: bytes,
    objetivo_usuario: str = "mantenerse",
    tono: str = "firme",
    caption: str = "",
) -> dict:
    """Llama Vision API y devuelve dict con alimentos, macros y feedback.

    Acepta `caption` opcional para que el usuario pueda adjuntar texto a la
    foto (ej: "es el paquete de filetes, 250g") y eso entre al contexto del
    modelo.

    Si error, devuelve {"error": "no_food" | "json_invalido" | "api_error"}.
    Incluye `vision_elapsed_ms` en el log para diagnosticar latencia.
    """
    t0 = time.perf_counter()
    try:
        b64 = base64.b64encode(foto_bytes).decode("ascii")
        user_text = f"Mi objetivo es: {objetivo_usuario}. Analiza esta comida."
        if caption:
            user_text += f"\nContexto del usuario: {caption.strip()[:300]}"
        response = await _get_client().chat.completions.create(
            model=settings.vision_model,
            messages=[
                {"role": "system", "content": _prompt_sistema(tono)},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": user_text,
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=500,
            temperature=0.3,
        )
        if response.usage:
            try:
                await log_llm_usage(
                    None,
                    "vision",
                    settings.vision_model,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                )
            except Exception:
                logger.exception("Error loggeando uso LLM en vision (no critico)")
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        if "error" in data:
            logger.info(
                "analizar_comida no_food/error vision_elapsed_ms=%.1f error=%s",
                elapsed_ms,
                data["error"],
            )
            return {"error": data["error"]}
        logger.info(
            "analizar_comida OK vision_elapsed_ms=%.1f n_alim=%d kcal=%s fuente=%s",
            elapsed_ms,
            len(data.get("alimentos", []) or []),
            data.get("calorias"),
            data.get("fuente", "?"),
        )
        return {
            "alimentos": data.get("alimentos", []),
            "calorias": int(data.get("calorias", 0) or 0),
            "proteinas_g": float(data.get("proteinas_g", 0) or 0),
            "carbohidratos_g": float(data.get("carbohidratos_g", 0) or 0),
            "grasas_g": float(data.get("grasas_g", 0) or 0),
            "fuente": data.get("fuente", "estimacion"),
            "feedback": data.get("feedback", "").strip(),
        }
    except json.JSONDecodeError:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.exception(
            "Vision devolvio JSON invalido vision_elapsed_ms=%.1f", elapsed_ms
        )
        return {"error": "json_invalido"}
    except Exception:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.exception("Error en analizar_comida vision_elapsed_ms=%.1f", elapsed_ms)
        return {"error": "api_error"}


async def describir_imagen_no_comida(foto_bytes: bytes) -> str:
    """Usa Vision para describir una imagen que NO fue detectada como comida.

    Esto ayuda al coach a 'ver' que hay en la foto (ej: un gym, un skate,
    una persona entrenando, un suplemento).
    """
    try:
        b64 = base64.b64encode(foto_bytes).decode("ascii")
        response = await _get_client().chat.completions.create(
            model=settings.vision_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente que describe imagenes para un coach deportivo. "
                        "Describe brevemente (1-2 frases) que ves en la imagen, "
                        "enfocandote en elementos deportivos, equipamiento, "
                        "entorno de entrenamiento o productos nutricionales."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            max_tokens=150,
            temperature=0.5,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception:
        logger.exception("Error describiendo imagen no comida")
        return "No pude ver claramente que hay en la imagen."


def resize_si_pesa(foto_bytes: bytes, max_kb: int = 1024) -> bytes:
    """Reduce la imagen si pesa mas de max_kb. Mantiene aspect ratio."""
    if len(foto_bytes) <= max_kb * 1024:
        return foto_bytes
    try:
        from PIL import Image

        img = Image.open(BytesIO(foto_bytes))
        img.thumbnail((1280, 1280))
        out = BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=80, optimize=True)
        return out.getvalue()
    except Exception:
        logger.exception("Error redimensionando imagen")
        return foto_bytes
