"""API REST chat multicanal para app Android."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.auth import get_uid_from_token
from src.config import settings
from src.db.models import CanalConversacion
from src.services.conversation_handoff import handoff_app_a_telegram
from src.services.conversation_service import (
    archivar_conversacion,
    crear_conversacion,
    fijar_conversacion_activa,
    listar_conversaciones,
    listar_mensajes,
    obtener_conversacion,
    renombrar_conversacion,
    titulo_auto_desde_mensaje,
)
from src.services.coach_turn import run_coach_turn
from src.services.crisis import detectar as detectar_crisis
from src.services.identity import resolver_user_id_desde_api_jwt
from src.services.tts import transcribir_audio
from src.telegram.middlewares import check_daily_quota, check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/me", tags=["chat"])


class CrearConversacionReq(BaseModel):
    titulo: str | None = None


class ChatReq(BaseModel):
    mensaje: str = Field(min_length=1, max_length=4000)


class PatchConversacionReq(BaseModel):
    titulo: str | None = None
    archivar: bool | None = None


class ActivaConversacionReq(BaseModel):
    conversacion_id: int


async def _require_user(jwt_sub: int) -> tuple[int, int]:
    user_id = await resolver_user_id_desde_api_jwt(jwt_sub)
    if user_id is None:
        raise HTTPException(404, "Usuario no encontrado")
    return jwt_sub, user_id


def _conv_dict(c) -> dict[str, Any]:
    return {
        "id": c.id,
        "titulo": c.titulo,
        "canal_creador": c.canal_creador.value if c.canal_creador else "telegram",
        "activa": c.activa,
        "es_principal": c.es_principal,
        "ultimo_mensaje_en": c.ultimo_mensaje_en.isoformat() if c.ultimo_mensaje_en else None,
        "resumen_handoff": c.resumen_handoff,
    }


def _msg_dict(m) -> dict[str, Any]:
    return {
        "id": m.id,
        "rol": m.rol.value if m.rol else "user",
        "contenido": m.contenido,
        "canal_origen": m.canal_origen.value if m.canal_origen else "android",
        "es_desde_telegram": m.es_desde_telegram,
        "metadata": m.metadata_json,
        "creado_en": m.creado_en.isoformat() if m.creado_en else None,
    }


@router.get("/conversaciones")
async def api_listar_conversaciones(
    jwt_sub: int = Depends(get_uid_from_token),
    limit: int = 30,
    offset: int = 0,
) -> dict:
    if not settings.chat_android_enabled:
        raise HTTPException(503, "Chat app deshabilitado")
    _, user_id = await _require_user(jwt_sub)
    convs = await listar_conversaciones(user_id, limit=limit, offset=offset)
    return {"conversaciones": [_conv_dict(c) for c in convs]}


@router.post("/conversaciones")
async def api_crear_conversacion(
    req: CrearConversacionReq,
    jwt_sub: int = Depends(get_uid_from_token),
) -> dict:
    if not settings.chat_android_enabled:
        raise HTTPException(503, "Chat app deshabilitado")
    telegram_id, user_id = await _require_user(jwt_sub)
    if not settings.chat_multithread_enabled:
        from src.services.conversation_service import asegurar_conversacion_principal

        conv = await asegurar_conversacion_principal(telegram_id)
        return {"conversacion": _conv_dict(conv)}

    titulo = (req.titulo or "Nuevo hilo")[:120]
    conv = await crear_conversacion(user_id, titulo=titulo, canal=CanalConversacion.ANDROID)
    await fijar_conversacion_activa(telegram_id, conv.id)
    return {"conversacion": _conv_dict(conv)}


@router.patch("/conversaciones/{conv_id}")
async def api_patch_conversacion(
    conv_id: int,
    req: PatchConversacionReq,
    jwt_sub: int = Depends(get_uid_from_token),
) -> dict:
    _, user_id = await _require_user(jwt_sub)
    if req.titulo:
        await renombrar_conversacion(conv_id, user_id, req.titulo)
    if req.archivar:
        ok = await archivar_conversacion(conv_id, user_id)
        if not ok:
            raise HTTPException(400, "No se puede archivar este hilo")
    conv = await obtener_conversacion(conv_id, user_id)
    if conv is None:
        raise HTTPException(404, "Conversacion no encontrada")
    return {"conversacion": _conv_dict(conv)}


@router.get("/conversaciones/{conv_id}/mensajes")
async def api_listar_mensajes(
    conv_id: int,
    jwt_sub: int = Depends(get_uid_from_token),
    before: int | None = None,
    limit: int = 50,
) -> dict:
    _, user_id = await _require_user(jwt_sub)
    conv = await obtener_conversacion(conv_id, user_id)
    if conv is None:
        raise HTTPException(404, "Conversacion no encontrada")
    msgs = await listar_mensajes(conv_id, before_id=before, limit=min(limit, 100))
    return {"mensajes": [_msg_dict(m) for m in msgs]}


@router.post("/conversaciones/activa")
async def api_fijar_activa(
    req: ActivaConversacionReq,
    jwt_sub: int = Depends(get_uid_from_token),
) -> dict:
    telegram_id, user_id = await _require_user(jwt_sub)
    conv = await obtener_conversacion(req.conversacion_id, user_id)
    if conv is None:
        raise HTTPException(404, "Conversacion no encontrada")
    await fijar_conversacion_activa(telegram_id, conv.id)
    return {"ok": True, "conversacion_id": conv.id}


async def _ejecutar_chat(
    telegram_id: int,
    user_id: int,
    conv_id: int,
    mensaje: str,
    metadata: dict | None = None,
):
    conv = await obtener_conversacion(conv_id, user_id)
    if conv is None:
        raise HTTPException(404, "Conversacion no encontrada")

    crisis = detectar_crisis(mensaje)
    if crisis:
        raise HTTPException(
            400,
            detail={
                "code": "crisis",
                "message": "Tu mensaje requiere atencion prioritaria. Busca ayuda medica si es urgente.",
            },
        )

    if not await check_rate_limit(telegram_id):
        raise HTTPException(429, "Demasiados mensajes. Espera un momento.")
    puede, usado, limite = await check_daily_quota(telegram_id)
    if not puede:
        raise HTTPException(
            402,
            f"Limite diario alcanzado ({limite} mensajes). Mejora tu plan para continuar.",
        )

    if conv.titulo in ("Coach", "Nuevo hilo") and len(mensaje) > 3:
        await renombrar_conversacion(conv_id, user_id, await titulo_auto_desde_mensaje(mensaje))

    result = await run_coach_turn(
        telegram_id=telegram_id,
        conversacion_id=conv_id,
        texto=mensaje,
        canal="android",
        conversacion_titulo=conv.titulo,
        metadata_usuario=metadata,
    )
    return result, conv


@router.post("/conversaciones/{conv_id}/chat")
async def api_chat(
    conv_id: int,
    req: ChatReq,
    jwt_sub: int = Depends(get_uid_from_token),
) -> dict:
    if not settings.chat_android_enabled:
        raise HTTPException(503, "Chat app deshabilitado")
    telegram_id, user_id = await _require_user(jwt_sub)
    result, conv = await _ejecutar_chat(telegram_id, user_id, conv_id, req.mensaje.strip())
    return {
        "ok": True,
        "respuesta": result.respuesta,
        "mensaje_usuario_id": result.mensaje_usuario_id,
        "mensaje_coach_id": result.mensaje_coach_id,
        "tools_usadas": result.tools_invocadas,
        "request_id": result.request_id,
        "conversacion": _conv_dict(conv),
    }


@router.post("/conversaciones/{conv_id}/chat/stream")
async def api_chat_stream(
    conv_id: int,
    req: ChatReq,
    jwt_sub: int = Depends(get_uid_from_token),
):
    """SSE minimal: un evento con la respuesta completa (fase 9 polish)."""
    if not settings.chat_android_enabled:
        raise HTTPException(503, "Chat app deshabilitado")
    telegram_id, user_id = await _require_user(jwt_sub)
    result, _conv = await _ejecutar_chat(telegram_id, user_id, conv_id, req.mensaje.strip())

    async def gen():
        payload = {"type": "done", "respuesta": result.respuesta, "request_id": result.request_id}
        yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/conversaciones/{conv_id}/audio")
async def api_chat_audio(
    conv_id: int,
    jwt_sub: int = Depends(get_uid_from_token),
    file: UploadFile = File(...),
) -> dict:
    if not settings.chat_android_enabled:
        raise HTTPException(503, "Chat app deshabilitado")
    telegram_id, user_id = await _require_user(jwt_sub)

    content_type = (file.content_type or "").lower()
    allowed = ("audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "audio/x-m4a", "audio/m4a")
    if content_type and not any(content_type.startswith(a.split("/")[0]) for a in allowed):
        if "audio" not in content_type and "octet" not in content_type:
            raise HTTPException(400, f"Tipo de audio no soportado: {content_type}")

    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024:
        raise HTTPException(413, "Audio demasiado grande (max 25MB)")
    if not raw:
        raise HTTPException(400, "Archivo vacio")

    filename = file.filename or "voice.m4a"
    transcripcion = await transcribir_audio(raw, filename=filename)
    if not transcripcion:
        raise HTTPException(422, "No se detecto voz en el audio")

    result, conv = await _ejecutar_chat(
        telegram_id,
        user_id,
        conv_id,
        transcripcion,
        metadata={"transcripcion": True, "audio_filename": filename},
    )
    return {
        "ok": True,
        "transcripcion": transcripcion,
        "respuesta": result.respuesta,
        "mensaje_usuario_id": result.mensaje_usuario_id,
        "mensaje_coach_id": result.mensaje_coach_id,
        "conversacion": _conv_dict(conv),
    }


@router.post("/conversaciones/{conv_id}/handoff/telegram")
async def api_handoff_telegram(
    conv_id: int,
    request: Request,
    jwt_sub: int = Depends(get_uid_from_token),
) -> dict:
    if not settings.chat_handoff_enabled:
        raise HTTPException(503, "Handoff deshabilitado")
    telegram_id, user_id = await _require_user(jwt_sub)
    if telegram_id <= 0:
        raise HTTPException(400, "Vincula Telegram primero para continuar alli")

    bot = getattr(request.app.state, "telegram_bot", None)
    return await handoff_app_a_telegram(conv_id, user_id, telegram_id, bot)


@router.get("/realtime/cuota")
async def api_realtime_cuota(jwt_sub: int = Depends(get_uid_from_token)) -> dict:
    from src.realtime.cuotas import cuota_total_segundos, disponible_segundos

    telegram_id, _ = await _require_user(jwt_sub)
    total = await cuota_total_segundos(telegram_id)
    disp = await disponible_segundos(telegram_id)
    return {
        "segundos_disponibles": disp,
        "segundos_total_mes": total,
        "minutos_disponibles": round(disp / 60, 1),
    }
