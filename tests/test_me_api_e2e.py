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

    response = await api_client.post("/api/me/telegram/pair-token", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "pair_token" in body
    
    pair_token = body["pair_token"]
    assert pair_token.startswith("pair_")

    # Verificar que se guardó en Redis
    saved_uid = await mock_redis.get(f"telegram:pair:{pair_token}")
    assert saved_uid == str(telegram_id)


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
