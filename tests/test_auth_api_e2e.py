from __future__ import annotations

import pytest
from src.db.models import Usuario

@pytest.mark.asyncio
async def test_request_otp_unknown_phone_no_email(api_client):
    response = await api_client.post(
        "/api/auth/phone/request-otp",
        json={"telefono": "3044093197"}
    )
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "PHONE_NOT_REGISTERED"
    assert "no está registrado" in body["detail"]


@pytest.mark.asyncio
async def test_request_otp_new_phone_with_email(api_client, mock_redis):
    response = await api_client.post(
        "/api/auth/phone/request-otp",
        json={"telefono": "3044093197", "email": "diego@ejemplo.com"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["email_hint"] == "d***o@ejemplo.com"

    # Verificar que el código se guardó en Redis con TTL y la clave adecuada
    normalized_phone = "+573044093197"
    codigo = await mock_redis.get(f"otp:phone:{normalized_phone}")
    assert codigo is not None
    assert len(codigo) == 6

    saved_email = await mock_redis.get(f"otp:phone:email:{normalized_phone}")
    assert saved_email == "diego@ejemplo.com"


@pytest.mark.asyncio
async def test_verify_otp_wrong_code(api_client, mock_redis):
    normalized_phone = "+573044093197"
    await mock_redis.set(f"otp:phone:{normalized_phone}", "123456")
    await mock_redis.set(f"otp:phone:email:{normalized_phone}", "diego@ejemplo.com")

    response = await api_client.post(
        "/api/auth/phone/verify-otp",
        json={"telefono": "3044093197", "codigo": "654321"}
    )
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_OTP"


@pytest.mark.asyncio
async def test_verify_otp_creates_user(api_client, mock_redis, db_session):
    normalized_phone = "+573044093197"
    await mock_redis.set(f"otp:phone:{normalized_phone}", "123456")
    await mock_redis.set(f"otp:phone:email:{normalized_phone}", "diego@ejemplo.com")

    response = await api_client.post(
        "/api/auth/phone/verify-otp",
        json={"telefono": "3044093197", "codigo": "123456"}
    )
    assert response.status_code == 200
    body = response.json()
    assert "jwt" in body
    assert body["profile_complete"] is True

    # Verificar creación de usuario en base de datos
    from sqlalchemy import select
    res = await db_session.execute(select(Usuario).where(Usuario.telefono == normalized_phone))
    user = res.scalar_one_or_none()
    assert user is not None
    assert user.email == "diego@ejemplo.com"
    assert user.phone_verified_at is not None


@pytest.mark.asyncio
async def test_request_otp_existing_phone(api_client, db_session, mock_redis):
    # Crear usuario de prueba
    normalized_phone = "+573044093197"
    user = Usuario(
        telegram_id=1234567,
        telefono=normalized_phone,
        email="test@ejemplo.com",
    )
    db_session.add(user)
    await db_session.commit()

    # Request OTP sin email (debería resolver el del usuario en DB)
    response = await api_client.post(
        "/api/auth/phone/request-otp",
        json={"telefono": "3044093197"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["email_hint"] == "t**t@ejemplo.com"


@pytest.mark.asyncio
async def test_codigo_web_flow_and_android_ttl(api_client, mock_redis, db_session):
    from src.services.codigo_web import generar_codigo
    telegram_id = 998877

    # Crear usuario en DB
    user = Usuario(
        telegram_id=telegram_id,
        telefono="+573001112233",
        email="diego@ejemplo.com",
        phone_verified_at=None  # incompleto
    )
    db_session.add(user)
    await db_session.commit()

    # Generar código web
    codigo = await generar_codigo(telegram_id)

    # Validar código sin X-Client (TTL normal web, 1h)
    response = await api_client.post(
        "/api/auth/codigo",
        json={"codigo": codigo}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == telegram_id
    assert body["expira_en"] == 3600
    assert body["profile_complete"] is False

    # Volver a generar para probar Android TTL (30 días)
    codigo_android = await generar_codigo(telegram_id)
    response_android = await api_client.post(
        "/api/auth/codigo",
        json={"codigo": codigo_android},
        headers={"X-Client": "android"}
    )
    assert response_android.status_code == 200
    body_android = response_android.json()
    assert body_android["expira_en"] == 2592000
    assert body_android["profile_complete"] is False


@pytest.mark.asyncio
async def test_complete_profile_flow(api_client, mock_redis, db_session):
    telegram_id = 554433
    # Crear un usuario iniciado desde Telegram (sin teléfono ni email)
    user = Usuario(
        telegram_id=telegram_id,
        auth_method="telegram",
    )
    db_session.add(user)
    await db_session.commit()

    # Generar JWT para el usuario
    from src.api.auth import _sign_jwt
    token = _sign_jwt(telegram_id)
    headers = {"Authorization": f"Bearer {token}"}

    # Intentar solicitar OTP para completar perfil con teléfono duplicado
    other_user = Usuario(
        telegram_id=1111,
        telefono="+573001112233",
        email="otro@ejemplo.com"
    )
    db_session.add(other_user)
    await db_session.commit()

    # 1. Duplicado teléfono
    response = await api_client.post(
        "/api/me/cuenta/solicitar-otp",
        json={"telefono": "3001112233", "email": "nuevo@ejemplo.com"},
        headers=headers
    )
    assert response.status_code == 400
    assert response.json()["code"] == "DUPLICATE_PHONE"

    # 2. Solicitud exitosa
    response = await api_client.post(
        "/api/me/cuenta/solicitar-otp",
        json={"telefono": "3004445566", "email": "nuevo@ejemplo.com"},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    codigo = await mock_redis.get(f"otp:complete:{telegram_id}")
    assert codigo is not None

    # 3. Confirmar OTP incorrecto
    response = await api_client.post(
        "/api/me/cuenta/confirmar-otp",
        json={"telefono": "3004445566", "codigo": "000000"},
        headers=headers
    )
    assert response.status_code == 401

    # 4. Confirmar OTP correcto
    response = await api_client.post(
        "/api/me/cuenta/confirmar-otp",
        json={"telefono": "3004445566", "codigo": codigo},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # Verificar que el perfil esté completo en DB
    from sqlalchemy import select
    db_session.expire_all()
    res = await db_session.execute(select(Usuario).where(Usuario.telegram_id == telegram_id))
    user_updated = res.scalar_one()
    assert user_updated.telefono == "+573004445566"
    assert user_updated.email == "nuevo@ejemplo.com"
    assert user_updated.phone_verified_at is not None
    assert user_updated.auth_method == "both"
