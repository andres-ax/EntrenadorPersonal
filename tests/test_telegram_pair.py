"""Tests de vinculacion Telegram app <-> bot."""
import json

import pytest

from sqlalchemy.exc import IntegrityError

from src.services.identity import link_telegram_to_user
from src.services.telegram_pair import (
    crear_solicitud_vinculacion,
    consumir_refresh_jwt,
    consumir_refresh_jwt_por_user_id,
    ejecutar_vinculacion,
    resolver_user_id_desde_jwt_sub,
)
from src.db.models import Usuario


@pytest.fixture
def patch_redis(mock_redis, monkeypatch):
    async def get_mock_redis():
        return mock_redis

    monkeypatch.setattr("src.cache.get_redis", get_mock_redis)
    monkeypatch.setattr("src.services.telegram_pair.get_redis", get_mock_redis)


@pytest.mark.asyncio
async def test_crear_y_vincular_con_codigo(patch_redis, mock_redis, db_session):
    virtual_id = -918273645
    user = Usuario(
        telegram_id=virtual_id,
        nombre="Diego",
        telefono="+573044093197",
        email="test@ejemplo.com",
        auth_method="phone_email",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    data = await crear_solicitud_vinculacion(user.id, virtual_id)
    assert data["pair_code"].isdigit()
    assert len(data["pair_code"]) == 6
    assert data["pair_token"].startswith("pair_")

    real_telegram_id = 8324604749
    linked = await ejecutar_vinculacion(data["pair_code"], real_telegram_id)
    assert linked is not None
    assert linked.telegram_id == real_telegram_id
    assert linked.auth_method in ("both", "phone_email")

    new_sub = await consumir_refresh_jwt(virtual_id)
    assert new_sub == real_telegram_id


@pytest.mark.asyncio
async def test_vincular_token_expirado(patch_redis):
    linked = await ejecutar_vinculacion("999999", 12345)
    assert linked is None


@pytest.mark.asyncio
async def test_reasociar_telegram_de_otro_usuario(db_session):
    """Telegram ya ligado a user A debe poder moverse a user B (app phone)."""
    real_telegram_id = 8324604749
    old_user = Usuario(
        telegram_id=real_telegram_id,
        nombre="Cuenta Telegram antigua",
        auth_method="telegram",
    )
    virtual_id = -918273645
    new_user = Usuario(
        telegram_id=virtual_id,
        nombre="Diego",
        telefono="+573044093197",
        email="test@ejemplo.com",
        auth_method="phone_email",
    )
    db_session.add(old_user)
    db_session.add(new_user)
    await db_session.commit()
    await db_session.refresh(old_user)
    await db_session.refresh(new_user)

    linked = await link_telegram_to_user(new_user.id, real_telegram_id)
    assert linked.telegram_id == real_telegram_id
    assert linked.id == new_user.id

    await db_session.refresh(old_user)
    assert old_user.telegram_id is None


@pytest.mark.asyncio
async def test_finish_pair_fallback_por_user_id(patch_redis, mock_redis, db_session):
    virtual_id = -555444333
    user = Usuario(
        telegram_id=virtual_id,
        nombre="Diego",
        telefono="+573044093197",
        email="test@ejemplo.com",
        auth_method="phone_email",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    data = await crear_solicitud_vinculacion(user.id, virtual_id)
    real_telegram_id = 8324604749
    await ejecutar_vinculacion(data["pair_code"], real_telegram_id)

    await mock_redis.delete(f"telegram:pair:refresh:{virtual_id}")

    assert await resolver_user_id_desde_jwt_sub(virtual_id) == user.id
    new_sub = await consumir_refresh_jwt_por_user_id(user.id)
    assert new_sub == real_telegram_id
