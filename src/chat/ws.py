"""WebSocket de sync de chat multicanal."""
from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.api.auth import verify_jwt
from src.config import settings
from src.services.chat_events import (
    _channel_user,
    mark_ws_offline,
    mark_ws_online,
    refresh_ws_online,
)
from src.services.identity import resolver_user_id_desde_api_jwt

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat-ws"])


@router.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    if not settings.chat_ws_enabled:
        await ws.close(code=1008, reason="chat_ws_disabled")
        return

    token = ws.query_params.get("token", "")
    telegram_id = verify_jwt(token)
    if telegram_id is None:
        await ws.close(code=1008, reason="JWT invalido")
        return

    user_id = await resolver_user_id_desde_api_jwt(telegram_id)
    if user_id is None:
        await ws.close(code=1008, reason="usuario_no_existe")
        return

    await ws.accept()
    await mark_ws_online(user_id)
    await ws.send_json({"type": "connected", "usuario_id": user_id})

    pubsub_client = aioredis.from_url(
        settings.redis_url_str,
        decode_responses=True,
    )
    pubsub = pubsub_client.pubsub()
    channel = _channel_user(user_id)
    await pubsub.subscribe(channel)

    cerrado = False

    async def escuchar_redis() -> None:
        nonlocal cerrado
        try:
            async for raw in pubsub.listen():
                if cerrado:
                    break
                if raw.get("type") != "message":
                    continue
                data = raw.get("data")
                if not data:
                    continue
                try:
                    if ws.client_state == WebSocketState.CONNECTED:
                        await ws.send_text(data)
                except Exception:
                    cerrado = True
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Error pubsub chat ws user_id=%s", user_id)
            cerrado = True

    async def escuchar_cliente() -> None:
        nonlocal cerrado
        try:
            while not cerrado:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    cerrado = True
                    break
                if "text" in msg and msg["text"]:
                    try:
                        payload = json.loads(msg["text"])
                        if payload.get("type") == "ping":
                            await ws.send_json({"type": "pong"})
                            await refresh_ws_online(user_id)
                    except json.JSONDecodeError:
                        pass
        except WebSocketDisconnect:
            cerrado = True

    redis_task = asyncio.create_task(escuchar_redis())
    try:
        await escuchar_cliente()
    finally:
        cerrado = True
        redis_task.cancel()
        try:
            await redis_task
        except asyncio.CancelledError:
            pass
        try:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
            await pubsub_client.aclose()
        except Exception:
            pass
        await mark_ws_offline(user_id)
        if ws.client_state == WebSocketState.CONNECTED:
            try:
                await ws.close()
            except Exception:
                pass
