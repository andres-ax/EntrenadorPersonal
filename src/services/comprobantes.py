"""Extraccion de datos de comprobantes de pago con OpenAI Vision.

Lee fotos de transferencias Bre-B, Nequi, Daviplata, Bancolombia, etc.
y devuelve dict estructurado con monto, fecha, hora, referencia, cuentas.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
from datetime import datetime, time
from typing import Optional

from openai import AsyncOpenAI

from src.config import settings
from src.db.repository import log_llm_usage

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _client


PROMPT_COMPROBANTE = (
    "Eres un sistema OCR especializado en comprobantes de pago colombianos "
    "(Bre-B del Banco de la Republica, Nequi, Daviplata, Bancolombia, "
    "transferencia interbancaria, PSE, llave). "
    "Analiza la imagen y devuelve SOLO JSON valido con este esquema:\n"
    "{\n"
    '  "es_comprobante": bool,\n'
    '  "monto_cop": int,  // pesos colombianos numericos\n'
    '  "monto_extraido_raw": str,  // tal como aparece en la imagen\n'
    '  "fecha": str,  // YYYY-MM-DD\n'
    '  "hora": str,  // HH:MM (24h)\n'
    '  "referencia": str,  // numero de aprobacion / referencia / id\n'
    '  "cuenta_origen": str,  // ultimos 4 digitos o llave del remitente\n'
    '  "cuenta_destino": str,  // ultimos 4 digitos o llave del receptor\n'
    '  "metodo": str,  // uno de: bre_b, nequi, daviplata, bancolombia, otro\n'
    '  "nombre_origen": str,  // si es visible\n'
    '  "nombre_destino": str,  // si es visible\n'
    '  "confianza": float  // 0.0-1.0 confidence general\n'
    "}\n"
    "Si la imagen NO es un comprobante de pago, devuelve "
    '{"es_comprobante": false, "razon": "..."}. '
    "Nunca inventes valores. Si un campo no es legible, usa string vacio "
    'y reduce "confianza".'
)

METODOS_VALIDOS = {"bre_b", "nequi", "daviplata", "bancolombia", "otro"}


def sha256_imagen(foto_bytes: bytes) -> str:
    """Hash sha256 hex de la imagen (32 bytes -> 64 chars)."""
    return hashlib.sha256(foto_bytes).hexdigest()


def _parse_fecha(raw: str) -> Optional[datetime]:
    """Best-effort parser de fecha en formato YYYY-MM-DD."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _parse_hora(raw: str) -> Optional[time]:
    if not raw:
        return None
    match = re.match(r"^(\d{1,2}):(\d{2})", raw)
    if not match:
        return None
    try:
        h = int(match.group(1))
        m = int(match.group(2))
        if 0 <= h < 24 and 0 <= m < 60:
            return time(h, m)
    except ValueError:
        pass
    return None


def _parse_monto(raw_str: str, raw_int) -> int:
    """Convierte un monto crudo a entero COP. Acepta "12.500", "$5,000", etc."""
    if isinstance(raw_int, int) and raw_int > 0:
        return raw_int
    if isinstance(raw_int, float) and raw_int > 0:
        return int(raw_int)
    if not raw_str:
        return 0
    limpio = re.sub(r"[^\d]", "", str(raw_str))
    if not limpio:
        return 0
    try:
        return int(limpio)
    except ValueError:
        return 0


async def extraer_datos_comprobante(foto_bytes: bytes) -> dict:
    """Llama Vision API y devuelve dict estructurado del comprobante.

    Returns
    -------
        dict con keys: ok (bool), es_comprobante (bool), monto_cop (int),
        fecha_pago (datetime|None), hora_pago (time|None), referencia (str),
        cuenta_origen (str), cuenta_destino (str), metodo (str), confianza (float),
        razon (str opcional), raw (dict Vision payload).

    """
    try:
        b64 = base64.b64encode(foto_bytes).decode("ascii")
        response = await _get_client().chat.completions.create(
            model=settings.comprobante_model,
            messages=[
                {"role": "system", "content": PROMPT_COMPROBANTE},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extrae los datos del comprobante.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=600,
            temperature=0.0,
        )
        if response.usage:
            try:
                await log_llm_usage(
                    None,
                    "comprobante",
                    settings.comprobante_model,
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                )
            except Exception:
                pass
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("Vision devolvio JSON invalido en comprobante")
        return {
            "ok": False,
            "es_comprobante": False,
            "razon": "json_invalido",
            "raw": {},
        }
    except Exception:
        logger.exception("Error en extraer_datos_comprobante")
        return {"ok": False, "es_comprobante": False, "razon": "api_error", "raw": {}}

    if not data.get("es_comprobante", False):
        return {
            "ok": True,
            "es_comprobante": False,
            "razon": data.get("razon", "no_es_comprobante"),
            "raw": data,
        }

    metodo = (data.get("metodo") or "otro").lower().strip()
    if metodo not in METODOS_VALIDOS:
        metodo = "otro"

    return {
        "ok": True,
        "es_comprobante": True,
        "monto_cop": _parse_monto(
            data.get("monto_extraido_raw", ""), data.get("monto_cop")
        ),
        "monto_extraido_raw": str(data.get("monto_extraido_raw", "")),
        "fecha_pago": _parse_fecha(data.get("fecha", "")),
        "hora_pago": _parse_hora(data.get("hora", "")),
        "referencia": str(data.get("referencia", "")).strip(),
        "cuenta_origen": str(data.get("cuenta_origen", "")).strip(),
        "cuenta_destino": str(data.get("cuenta_destino", "")).strip(),
        "nombre_origen": str(data.get("nombre_origen", "")).strip(),
        "nombre_destino": str(data.get("nombre_destino", "")).strip(),
        "metodo": metodo,
        "confianza": float(data.get("confianza", 0.5) or 0.5),
        "raw": data,
    }
