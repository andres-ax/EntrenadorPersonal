"""OpenAI Vision para analisis de fotos de comida.

Devuelve estimacion de alimentos, calorias, macros y un feedback corto.
"""
from __future__ import annotations

import base64
import json
import logging
from io import BytesIO

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _client


def _prompt_sistema(tono: str) -> str:
    base = (
        "Eres un nutricionista deportivo ISSN-CISSN. Analiza la foto de la "
        "comida que envia el usuario. Devuelve SOLO JSON valido con esta forma:\n"
        '{"alimentos": ["alimento1","alimento2",...], "calorias": int, '
        '"proteinas_g": float, "carbohidratos_g": float, "grasas_g": float, '
        '"feedback": "1-2 frases sobre la comida y su impacto en el objetivo"}\n'
        "Si la foto no tiene comida visible, devuelve {\"error\": \"no_food\"}. "
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
) -> dict:
    """Llama Vision API y devuelve dict con alimentos, macros y feedback.

    Si error, devuelve {"error": "..."}.
    """
    try:
        b64 = base64.b64encode(foto_bytes).decode("ascii")
        response = await _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _prompt_sistema(tono)},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Mi objetivo es: {objetivo_usuario}. Analiza esta comida.",
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
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        if "error" in data:
            return {"error": data["error"]}
        return {
            "alimentos": data.get("alimentos", []),
            "calorias": int(data.get("calorias", 0) or 0),
            "proteinas_g": float(data.get("proteinas_g", 0) or 0),
            "carbohidratos_g": float(data.get("carbohidratos_g", 0) or 0),
            "grasas_g": float(data.get("grasas_g", 0) or 0),
            "feedback": data.get("feedback", "").strip(),
        }
    except json.JSONDecodeError:
        logger.exception("Vision devolvio JSON invalido")
        return {"error": "json_invalido"}
    except Exception:
        logger.exception("Error en analizar_comida")
        return {"error": "api_error"}


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
