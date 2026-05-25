from __future__ import annotations

import pytest
from src.db.models import Usuario

@pytest.mark.asyncio
async def test_perfil_requires_jwt(api_client):
    response = await api_client.get("/api/me/perfil")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_ok(api_client, db_session):
    telegram_id = 112233
    user = Usuario(
        telegram_id=telegram_id,
        nombre="Diego",
        telefono="+573001112233",
        email="diego@ejemplo.com",
    )
    db_session.add(user)
    await db_session.commit()

    from src.api.auth import _sign_jwt
    token = _sign_jwt(telegram_id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await api_client.get("/api/me/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "reporte_semanal" in body
    assert "streak_entreno" in body
    assert "nutricion_hoy" in body


@pytest.mark.asyncio
async def test_novedades_json(api_client, db_session):
    telegram_id = 112233
    user = Usuario(
        telegram_id=telegram_id,
        nombre="Diego",
        telefono="+573001112233",
        email="diego@ejemplo.com",
    )
    db_session.add(user)
    await db_session.commit()

    from src.api.auth import _sign_jwt
    token = _sign_jwt(telegram_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    response = await api_client.get("/api/me/novedades", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "noticias" in body
    assert "desafios" in body


@pytest.mark.asyncio
async def test_pair_token(api_client, db_session, mock_redis):
    import json

    virtual_id = -918273645
    user = Usuario(
        telegram_id=virtual_id,
        nombre="Diego",
        telefono="+573001112233",
        email="diego@ejemplo.com",
    )
    db_session.add(user)
    await db_session.commit()

    from src.api.auth import _sign_jwt
    token = _sign_jwt(virtual_id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await api_client.post("/api/me/telegram/pair-token", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["pair_token"].startswith("pair_")
    assert len(body["pair_code"]) == 6
    assert "telegram_url" in body
    assert body["vincular_command"].startswith("/vincular ")

    saved = await mock_redis.get(f"telegram:pair:{body['pair_token']}")
    payload = json.loads(saved)
    assert payload["user_id"] == user.id
    assert payload["jwt_sub"] == virtual_id


@pytest.mark.asyncio
async def test_wearables_list(api_client, db_session):
    telegram_id = 112233
    user = Usuario(
        telegram_id=telegram_id,
        nombre="Diego",
        telefono="+573001112233",
        email="diego@ejemplo.com",
    )
    db_session.add(user)
    await db_session.commit()

    from src.api.auth import _sign_jwt
    token = _sign_jwt(telegram_id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await api_client.get("/api/me/wearables", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "proveedores_disponibles" in body
    assert "integraciones" in body
