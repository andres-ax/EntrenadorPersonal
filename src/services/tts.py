"""TTS via OpenAI con cache en disco por hash. Voz por tono."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from io import BytesIO
from pathlib import Path

import openai
import telegram.error
from openai import AsyncOpenAI
from telegram.constants import ChatAction, ParseMode

from src.config import settings
from src.db.repository import log_llm_usage

logger = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/entrenadorax_tts")
CACHE_DIR.mkdir(exist_ok=True)

_client: AsyncOpenAI | None = None


VOZ_POR_TONO = {
    "amigable": "nova",
    "firme": "alloy",
    "militar": "onyx",
}


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _client


async def transcribir_audio(
    file_bytes: bytes,
    filename: str = "voice.ogg",
    language: str = "es",
) -> str:
    """Transcribe audio con Whisper de OpenAI.

    Implementa reintentos con backoff y fallback a whisper-1 si el modelo
    por defecto (gpt-4o-mini-transcribe) falla.

    Args:
        file_bytes: bytes del audio (ogg/opus/m4a/mp3/wav).
        filename: nombre logico (el suffix orienta al modelo a detectar el formato).
        language: ISO-639-1; "es" por defecto para EntrenadorAX.

    Returns:
        Texto transcrito (string vacio si el audio no contiene voz audible o
        falla la API). NUNCA levanta excepciones para no romper el handler.
    """
    if not file_bytes:
        return ""

    modelos = [settings.transcription_model, "whisper-1"]
    # Si el configurado ya es whisper-1, no duplicamos
    if settings.transcription_model == "whisper-1":
        modelos = ["whisper-1"]

    for model in modelos:
        intentos = 3
        for i in range(intentos):
            try:
                response = await _get_client().audio.transcriptions.create(
                    model=model,
                    file=(filename, file_bytes),
                    language=language,
                )
                text = (response.text or "").strip()
                try:
                    await log_llm_usage(None, "whisper", model, 0, 0)
                except Exception:
                    pass
                return text
            except (openai.RateLimitError, openai.APITimeoutError) as e:
                if i == intentos - 1:
                    logger.warning(
                        "Limite o timeout en transcripcion (modelo=%s, bytes=%d): %s",
                        model, len(file_bytes), str(e)
                    )
                    break
                wait = (i + 1) * 2
                await asyncio.sleep(wait)
            except Exception as e:
                logger.warning(
                    "Error transcribiendo con %s (%d bytes): %s",
                    model, len(file_bytes), str(e)
                )
                break  # Otros errores no reintentamos con el mismo modelo

    logger.error("Fallo total de transcripcion tras agotar modelos y reintentos")
    return ""


async def generar_voz(texto: str, voice: str = "alloy") -> BytesIO | None:
    """Genera audio opus a partir de texto. Cachea por sha256(voz+texto)."""
    if not texto.strip():
        return None
    cache_key = hashlib.sha256(f"{voice}:{texto}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.opus"

    if cache_path.exists():
        return BytesIO(cache_path.read_bytes())

    try:
        response = await _get_client().audio.speech.create(
            model="tts-1",
            voice=voice,
            input=texto,
            response_format="opus",
        )
        audio_bytes = response.read()
        cache_path.write_bytes(audio_bytes)
        try:
            await log_llm_usage(None, "tts", "tts-1", len(texto), 0)
        except Exception:
            pass
        return BytesIO(audio_bytes)
    except Exception:
        logger.exception("Error generando TTS")
        return None


async def enviar_voz(
    bot,
    chat_id: int,
    texto: str,
    tono: str = "firme",
    fallback_text: bool = True,
) -> bool:
    """Envia voz con send_action record_voice. Si falla, fallback a texto.

    Returns:
        True si envio voz exitosamente, False si hubo que hacer fallback a texto.
    """
    voice = VOZ_POR_TONO.get(tono, "alloy")
    try:
        await bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    except Exception:
        pass

    audio = await generar_voz(texto, voice=voice)
    if audio is None:
        if fallback_text:
            try:
                await bot.send_message(
                    chat_id=chat_id, text=texto, parse_mode=ParseMode.HTML
                )
            except Exception:
                logger.exception("Fallback texto tambien fallo uid=%s", chat_id)
        return False

    try:
        caption = f"||{texto[:1024]}||" if len(texto) <= 1024 else None
        await bot.send_voice(
            chat_id=chat_id,
            voice=audio,
            caption=caption,
            parse_mode=ParseMode.HTML if caption else None,
        )
        return True
    except telegram.error.Forbidden:
        logger.info("Bot bloqueado por %s", chat_id)
        return False
    except Exception:
        logger.exception("Error enviando voz uid=%s", chat_id)
        if fallback_text:
            try:
                await bot.send_message(
                    chat_id=chat_id, text=texto, parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
        return False
