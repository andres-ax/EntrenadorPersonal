"""Tests WebSocket /ws/chat."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.auth import _sign_jwt
from src.db.models import Usuario
from src.main import app


async def async_iter_empty():
    if False:
        yield {}


@pytest.mark.asyncio
async def test_ws_chat_rejects_invalid_jwt():
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/chat?token=invalido") as ws:
            ws.receive_json()


@pytest.mark.asyncio
async def test_ws_chat_connected(db_session):
    user = Usuario(telegram_id=99001, nombre="Ws", telefono="+573001112233", email="ws@test.com")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = _sign_jwt(user.telegram_id)
    client = TestClient(app)
    with patch("src.chat.ws.aioredis.from_url") as mock_from_url:
        pubsub = AsyncMock()
        pubsub.listen = AsyncMock(return_value=async_iter_empty())
        pubsub.subscribe = AsyncMock()
        pubsub.unsubscribe = AsyncMock()
        pubsub.aclose = AsyncMock()
        redis_client = AsyncMock()
        redis_client.pubsub = lambda: pubsub
        redis_client.aclose = AsyncMock()
        mock_from_url.return_value = redis_client

        with client.websocket_connect(f"/ws/chat?token={token}") as ws:
            data = ws.receive_json()
            assert data["type"] == "connected"
            assert data["usuario_id"] == user.id
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"
