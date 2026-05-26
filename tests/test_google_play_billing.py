"""Tests Google Play Billing (modo dev + mocks)."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from src.api.auth import _sign_jwt
from src.db.models import MetodoPago, PlanSuscripcion, Suscripcion, Usuario
from src.db.repository import (
    activar_plan_google,
    activar_suscripcion_pro,
    obtener_plan_efectivo_por_user_id,
)
from src.services.google_play_billing import VerifiedPurchase


@pytest.mark.asyncio
async def test_verify_dev_token_activates_pro(api_client, db_session):
    telegram_id = 556677
    user = Usuario(
        telegram_id=telegram_id,
        nombre="Ana",
        telefono="+573001112244",
        email="ana@ejemplo.com",
    )
    db_session.add(user)
    await db_session.commit()

    token = _sign_jwt(telegram_id)
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "purchase_token": "dev_pro_mensual_test001",
        "product_id": "pro_mensual",
    }
    response = await api_client.post(
        "/api/me/billing/google/verify",
        json=body,
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["plan_actual"] == "pro"
    assert data["billing_source"] == "google_play"
    assert data["plan_expira_en"] is not None


@pytest.mark.asyncio
async def test_verify_idempotent(api_client, db_session):
    telegram_id = 556678
    user = Usuario(
        telegram_id=telegram_id,
        nombre="Luis",
        telefono="+573001112245",
        email="luis@ejemplo.com",
    )
    db_session.add(user)
    await db_session.commit()

    token = _sign_jwt(telegram_id)
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "purchase_token": "dev_pro_anual_idem001",
        "product_id": "pro_anual",
    }
    r1 = await api_client.post(
        "/api/me/billing/google/verify", json=body, headers=headers
    )
    r2 = await api_client.post(
        "/api/me/billing/google/verify", json=body, headers=headers
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["plan_actual"] == r2.json()["plan_actual"]


@pytest.mark.asyncio
async def test_verify_invalid_product(api_client, db_session):
    telegram_id = 556679
    user = Usuario(telegram_id=telegram_id, nombre="X")
    db_session.add(user)
    await db_session.commit()

    token = _sign_jwt(telegram_id)
    headers = {"Authorization": f"Bearer {token}"}
    response = await api_client.post(
        "/api/me/billing/google/verify",
        json={"purchase_token": "dev_fake", "product_id": "no_existe"},
        headers=headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_billing_planes(api_client, db_session):
    telegram_id = 556680
    user = Usuario(telegram_id=telegram_id, nombre="Y")
    db_session.add(user)
    await db_session.commit()

    token = _sign_jwt(telegram_id)
    headers = {"Authorization": f"Bearer {token}"}
    response = await api_client.get("/api/me/billing/planes", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["planes"]) == 4
    ids = {p["product_id"] for p in data["planes"]}
    assert ids == {"pro_mensual", "pro_anual", "elite_mensual", "elite_anual"}


@pytest.mark.asyncio
async def test_obtener_plan_efectivo_stars_and_google(db_session):
    telegram_id = 998877
    user = Usuario(telegram_id=telegram_id, nombre="Mix")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    await activar_suscripcion_pro(
        telegram_id,
        telegram_payment_charge_id="stars_charge_1",
        star_amount=100,
        dias=30,
    )
    expira_elite = datetime.utcnow() + timedelta(days=60)
    await activar_plan_google(
        user.id,
        purchase_token="dev_elite_mix",
        order_id="GPA.123",
        product_id="elite_mensual",
        base_plan_id="mensual",
        expira_en=expira_elite,
    )

    plan, expira, metodo = await obtener_plan_efectivo_por_user_id(user.id)
    assert plan == PlanSuscripcion.ELITE
    assert metodo == MetodoPago.GOOGLE_PLAY
    assert expira is not None


@pytest.mark.asyncio
async def test_rtdn_webhook_dedup(api_client):
    import base64
    import json

    payload = {
        "subscriptionNotification": {
            "notificationType": 4,
            "purchaseToken": "dev_rtdn_token",
            "subscriptionId": "pro_mensual",
        }
    }
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    body = {"message": {"messageId": "msg-001", "data": encoded}}

    with patch(
        "src.api.billing.verify_subscription",
        new=AsyncMock(
            return_value=VerifiedPurchase(
                is_active=True,
                product_id="pro_mensual",
                order_id="GPA.rtdn",
                base_plan_id="mensual",
                linked_purchase_token=None,
                expira_en=datetime.utcnow() + timedelta(days=30),
                subscription_state="SUBSCRIPTION_STATE_ACTIVE",
            )
        ),
    ):
        r1 = await api_client.post("/api/webhooks/google-play/rtdn", json=body)
        r2 = await api_client.post("/api/webhooks/google-play/rtdn", json=body)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True


@pytest.mark.asyncio
async def test_verify_expired_mock(api_client, db_session):
    telegram_id = 556681
    user = Usuario(telegram_id=telegram_id, nombre="Z")
    db_session.add(user)
    await db_session.commit()

    token = _sign_jwt(telegram_id)
    headers = {"Authorization": f"Bearer {token}"}

    with patch(
        "src.api.billing.verify_subscription",
        new=AsyncMock(
            return_value=VerifiedPurchase(
                is_active=False,
                product_id="pro_mensual",
                order_id="GPA.exp",
                base_plan_id="mensual",
                linked_purchase_token=None,
                expira_en=datetime.utcnow() - timedelta(days=1),
                subscription_state="SUBSCRIPTION_STATE_EXPIRED",
            )
        ),
    ):
        response = await api_client.post(
            "/api/me/billing/google/verify",
            json={"purchase_token": "real_token_exp", "product_id": "pro_mensual"},
            headers=headers,
        )
    assert response.status_code == 400
