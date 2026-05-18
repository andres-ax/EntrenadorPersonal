"""FastAPI WebSocket relay para llamadas Realtime con el coach.

Flujo:
  Cliente Mini App  --WSS PCM16-->  realtime-ws (este servicio)  --WSS-->  OpenAI Realtime API
                  <-- audio out --                              <-- audio chunks --

- Valida JWT del Mini App en query param `token`.
- Verifica cuota del tier en Redis.
- Stream bidireccional audio.
- Cuenta segundos usados y persiste sesion al terminar.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from starlette.websockets import WebSocketState

from src.api.auth import verify_jwt
from src.cache import close_redis, ping as ping_redis
from src.config import settings
from src.db.connection import async_session_factory, close_db, init_db, ping as ping_db
from src.db.models import RealtimeSesion, Usuario
from src.realtime.cuotas import (
    consumir_segundos,
    cuota_total_segundos,
    disponible_segundos,
)
from src.realtime.openai_client import RealtimeBridge

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_db()
    logger.info("realtime-ws iniciado")
    yield
    await close_db()
    await close_redis()


app = FastAPI(title="EntrenadorAX Realtime WS", lifespan=lifespan)

allowed_origins = []
if settings.miniapp_url:
    allowed_origins.append(str(settings.miniapp_url).rstrip("/"))
if settings.landing_url:
    allowed_origins.append(str(settings.landing_url).rstrip("/"))
if not allowed_origins:
    allowed_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    db_ok = await ping_db()
    redis_ok = await ping_redis()
    return {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "db": db_ok,
        "redis": redis_ok,
    }


@app.websocket("/ws/realtime")
async def ws_realtime(ws: WebSocket) -> None:
    token = ws.query_params.get("token", "")
    uid = verify_jwt(token)
    if uid is None:
        await ws.close(code=1008, reason="JWT invalido")
        return

    disponible = await disponible_segundos(uid)
    if disponible <= 0:
        await ws.accept()
        await ws.send_json(
            {
                "type": "error",
                "code": "sin_cuota",
                "message": "Sin minutos de voz este mes. Mejora tu plan en /pagar",
            }
        )
        await ws.close(code=1008, reason="sin_cuota")
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == uid)
        )
        usuario = result.scalar_one_or_none()
        if usuario is None:
            await ws.close(code=1008, reason="usuario_no_existe")
            return
        tono = usuario.tono.value if usuario.tono else "firme"
        usuario_pk = usuario.id

    await ws.accept()
    await ws.send_json(
        {
            "type": "cuota",
            "segundos_restantes": disponible,
            "segundos_total": await cuota_total_segundos(uid),
        }
    )

    bridge = RealtimeBridge(tono=tono)
    try:
        await bridge.conectar()
    except Exception:
        logger.exception("No pude conectar a OpenAI Realtime uid=%s", uid)
        await ws.send_json({"type": "error", "code": "openai_error", "message": "No pude conectar al coach"})
        await ws.close(code=1011)
        return

    inicio = time.time()
    transcript_parts: list[str] = []
    tokens_in = 0
    tokens_out = 0
    cerrado = False

    async def bombear_cliente_a_openai() -> None:
        nonlocal cerrado
        try:
            while not cerrado:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    cerrado = True
                    break
                if "bytes" in msg and msg["bytes"]:
                    await bridge.enviar_audio_pcm16(msg["bytes"])
                elif "text" in msg and msg["text"]:
                    try:
                        evento_cliente = json.loads(msg["text"])
                        if evento_cliente.get("type") == "fin":
                            cerrado = True
                            break
                    except json.JSONDecodeError:
                        pass
        except WebSocketDisconnect:
            cerrado = True

    async def bombear_openai_a_cliente() -> None:
        nonlocal tokens_in, tokens_out, cerrado
        async for evento in bridge.iterar_eventos():
            if cerrado:
                break
            tipo = evento.get("type", "")
            if tipo == "response.audio.delta":
                audio_b64 = evento.get("delta", "")
                if audio_b64:
                    try:
                        await ws.send_bytes(base64.b64decode(audio_b64))
                    except Exception:
                        cerrado = True
                        break
            elif tipo == "response.audio_transcript.delta":
                t = evento.get("delta", "")
                if t:
                    transcript_parts.append(f"coach:{t}")
                    try:
                        await ws.send_json({"type": "transcript", "role": "coach", "text": t})
                    except Exception:
                        cerrado = True
                        break
            elif tipo == "conversation.item.input_audio_transcription.completed":
                t = evento.get("transcript", "")
                if t:
                    transcript_parts.append(f"user:{t}")
                    try:
                        await ws.send_json({"type": "transcript", "role": "user", "text": t})
                    except Exception:
                        cerrado = True
                        break
            elif tipo == "response.done":
                resp = evento.get("response", {})
                usage = resp.get("usage", {})
                if "input_tokens" in usage:
                    tokens_in += int(usage["input_tokens"])
                if "output_tokens" in usage:
                    tokens_out += int(usage["output_tokens"])
                transcurridos = int(time.time() - inicio)
                restantes = (await cuota_total_segundos(uid)) - transcurridos
                if restantes <= 0:
                    try:
                        await ws.send_json(
                            {"type": "cuota", "segundos_restantes": 0}
                        )
                    except Exception:
                        pass
                    cerrado = True
                    break
            elif tipo == "error":
                err = evento.get("error", {})
                logger.warning("Realtime API error: %s", err)
                try:
                    await ws.send_json(
                        {"type": "error", "code": "openai_error", "message": err.get("message", "")}
                    )
                except Exception:
                    pass

    try:
        await asyncio.gather(
            bombear_cliente_a_openai(),
            bombear_openai_a_cliente(),
            return_exceptions=True,
        )
    finally:
        cerrado = True
        duracion = int(time.time() - inicio)
        await consumir_segundos(uid, duracion)
        await bridge.cerrar()
        try:
            await _persistir_sesion(
                usuario_id=usuario_pk,
                tono=tono,
                duracion=duracion,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                transcript="\n".join(transcript_parts)[:8000],
            )
        except Exception:
            logger.exception("Error persistiendo realtime_sesion uid=%s", uid)
        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close()
            except Exception:
                pass


async def _persistir_sesion(
    usuario_id: int,
    tono: str,
    duracion: int,
    tokens_in: int,
    tokens_out: int,
    transcript: str,
) -> None:
    costo_in = (tokens_in / 1_000_000) * 10.0
    costo_out = (tokens_out / 1_000_000) * 20.0
    async with async_session_factory() as session:
        sesion = RealtimeSesion(
            usuario_id=usuario_id,
            terminada_en=datetime.utcnow(),
            duracion_segundos=duracion,
            tono_usado=tono,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            costo_estimado_usd=costo_in + costo_out,
            transcript=transcript,
        )
        session.add(sesion)
        await session.commit()
