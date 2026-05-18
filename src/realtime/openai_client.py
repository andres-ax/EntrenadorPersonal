"""Cliente WebSocket de OpenAI Realtime API.

Doc: https://platform.openai.com/docs/guides/realtime
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import AsyncIterator, Callable, Optional

import websockets

from src.config import settings

logger = logging.getLogger(__name__)

REALTIME_URL = "wss://api.openai.com/v1/realtime?model=gpt-4o-mini-realtime-preview"


VOZ_POR_TONO = {
    "amigable": "alloy",
    "firme": "ash",
    "militar": "verse",
}


INSTRUCCIONES_BASE = (
    "Eres EntrenadorAX en modo llamada de voz. Hablas espanol neutro "
    "(CO/MX/AR/ES). Frases cortas, naturales con pausas. NUNCA insultas. "
    "NUNCA diagnosticas. Si el usuario menciona ideacion suicida, autolesion "
    "o trastorno alimenticio, baja el tono, valida emocionalmente y deriva "
    "a linea de crisis local. No uses HTML ni markdown, hablas en voz."
)


class RealtimeBridge:
    """Conecta cliente WebSocket (Mini App) con OpenAI Realtime API."""

    def __init__(self, tono: str = "firme"):
        self.tono = tono
        self.voice = VOZ_POR_TONO.get(tono, "ash")
        self.ws: Optional[websockets.WebSocketClientProtocol] = None

    async def conectar(self) -> None:
        api_key = settings.openai_api_key.get_secret_value()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        # websockets >= 14 renombro extra_headers -> additional_headers.
        # Detectamos cual usar para ser compatibles con ambas versiones.
        import inspect
        connect_params = inspect.signature(websockets.connect).parameters
        header_kwarg = "additional_headers" if "additional_headers" in connect_params else "extra_headers"
        self.ws = await websockets.connect(
            REALTIME_URL,
            **{header_kwarg: headers},
            max_size=10 * 1024 * 1024,
        )
        await self._enviar_evento(
            {
                "type": "session.update",
                "session": {
                    "voice": self.voice,
                    "instructions": INSTRUCCIONES_BASE,
                    "modalities": ["text", "audio"],
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 600,
                    },
                },
            }
        )

    async def _enviar_evento(self, evento: dict) -> None:
        if self.ws is None:
            raise RuntimeError("No conectado")
        await self.ws.send(json.dumps(evento))

    async def enviar_audio_pcm16(self, audio_bytes: bytes) -> None:
        """Envia chunk de audio PCM16 al modelo (input usuario)."""
        b64 = base64.b64encode(audio_bytes).decode("ascii")
        await self._enviar_evento(
            {"type": "input_audio_buffer.append", "audio": b64}
        )

    async def cerrar(self) -> None:
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None

    async def iterar_eventos(self) -> AsyncIterator[dict]:
        """Itera eventos del servidor de OpenAI."""
        if self.ws is None:
            return
        async for raw in self.ws:
            try:
                yield json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Evento Realtime invalido: %s", raw[:200])
