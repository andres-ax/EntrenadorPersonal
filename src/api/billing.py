"""Endpoints de billing (Google Play) y webhooks RTDN."""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.api.auth import get_uid_from_token
from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import GooglePlayRtdnEvent
from src.db.repository import (
    activar_plan_google,
    desactivar_plan_google,
    listar_tokens_google_activos,
    obtener_plan_efectivo_por_user_id,
    sync_usuario_plan_efectivo,
)
from src.services.google_play_billing import (
    VerifiedPurchase,
    should_deactivate,
    verify_subscription,
)
from src.services.google_play_products import list_billing_offers
from src.services.identity import resolver_user_id_desde_api_jwt

logger = logging.getLogger(__name__)

me_billing_router = APIRouter(prefix="/api/me/billing", tags=["billing"])
webhooks_router = APIRouter(prefix="/api/webhooks/google-play", tags=["webhooks"])

RENEW_TYPES = {1, 2, 4, 7, 8, 9, 12, 13}
DEACTIVATE_TYPES = {3, 5, 6, 10, 11}


class GoogleVerifyRequest(BaseModel):
    purchase_token: str = Field(min_length=8, max_length=512)
    product_id: str = Field(min_length=3, max_length=64)


class GoogleRestoreRequest(BaseModel):
    purchase_tokens: list[str] = Field(default_factory=list, max_length=20)


async def _require_user_id(jwt_sub: int) -> int:
    user_id = await resolver_user_id_desde_api_jwt(jwt_sub)
    if user_id is None:
        raise HTTPException(404, "Usuario no encontrado")
    return user_id


async def _activate_from_verified(user_id: int, purchase_token: str, verified: VerifiedPurchase) -> dict:
    if verified.is_active and verified.expira_en is not None:
        await activar_plan_google(
            user_id=user_id,
            purchase_token=purchase_token,
            order_id=verified.order_id,
            product_id=verified.product_id,
            base_plan_id=verified.base_plan_id,
            expira_en=verified.expira_en,
            linked_purchase_token=verified.linked_purchase_token,
        )
    elif should_deactivate(verified.subscription_state):
        await desactivar_plan_google(purchase_token)
        await sync_usuario_plan_efectivo(user_id)

    plan, expira_en, billing_source = await obtener_plan_efectivo_por_user_id(user_id)
    return {
        "ok": True,
        "plan_actual": plan.value,
        "plan_expira_en": expira_en.isoformat() if expira_en else None,
        "billing_source": billing_source.value if billing_source else None,
    }


@me_billing_router.get("/planes")
async def billing_planes(_uid: int = Depends(get_uid_from_token)) -> dict:
    offers = list_billing_offers()
    return {
        "planes": [
            {
                "product_id": o.product_id,
                "plan": o.plan,
                "duracion": o.duracion,
                "precio_cop_referencia": o.precio_cop_referencia,
                "precio_cop_formato": o.precio_cop_formato,
                "descripcion": o.descripcion,
                "features": o.features,
                "popular": o.popular,
            }
            for o in offers
        ],
        "google_play_enabled": settings.google_play_billing_enabled,
        "package_name": settings.google_play_package_name,
    }


@me_billing_router.post("/google/verify")
async def billing_google_verify(
    req: GoogleVerifyRequest,
    jwt_sub: int = Depends(get_uid_from_token),
) -> dict:
    user_id = await _require_user_id(jwt_sub)
    try:
        verified = await verify_subscription(req.purchase_token, req.product_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        logger.exception("verify google play user_id=%s", user_id)
        raise HTTPException(502, "No se pudo verificar la compra con Google") from exc

    if not verified.is_active:
        raise HTTPException(400, "La suscripcion no esta activa")
    if verified.expira_en is None:
        raise HTTPException(400, "Compra sin fecha de expiracion valida")

    return await _activate_from_verified(user_id, req.purchase_token, verified)


@me_billing_router.post("/google/restore")
async def billing_google_restore(
    req: GoogleRestoreRequest,
    jwt_sub: int = Depends(get_uid_from_token),
) -> dict:
    user_id = await _require_user_id(jwt_sub)
    tokens = req.purchase_tokens or await listar_tokens_google_activos(user_id)
    if not tokens:
        plan, expira_en, billing_source = await obtener_plan_efectivo_por_user_id(user_id)
        return {
            "ok": True,
            "restored": 0,
            "plan_actual": plan.value,
            "plan_expira_en": expira_en.isoformat() if expira_en else None,
            "billing_source": billing_source.value if billing_source else None,
        }

    restored = 0
    last_error: str | None = None
    for token in tokens:
        product_id = None
        async with async_session_factory() as session:
            from src.db.models import Suscripcion

            row = await session.execute(
                select(Suscripcion.google_product_id).where(
                    Suscripcion.google_purchase_token == token
                )
            )
            product_id = row.scalar_one_or_none()
        if not product_id:
            last_error = f"token sin product_id: {token[:12]}..."
            continue
        try:
            verified = await verify_subscription(token, product_id)
            await _activate_from_verified(user_id, token, verified)
            restored += 1
        except Exception as exc:
            last_error = str(exc)
            logger.warning("restore token fallo user_id=%s: %s", user_id, exc)

    plan, expira_en, billing_source = await obtener_plan_efectivo_por_user_id(user_id)
    return {
        "ok": True,
        "restored": restored,
        "plan_actual": plan.value,
        "plan_expira_en": expira_en.isoformat() if expira_en else None,
        "billing_source": billing_source.value if billing_source else None,
        "warning": last_error,
    }


@webhooks_router.post("/rtdn")
async def google_play_rtdn(request: Request) -> dict:
    """Webhook Pub/Sub RTDN (skeleton). Procesa renovaciones y revocaciones."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "JSON invalido")

    message = body.get("message") or {}
    message_id = message.get("messageId") or message.get("message_id")
    if not message_id:
        raise HTTPException(400, "messageId requerido")

    async with async_session_factory() as session:
        dup = await session.execute(
            select(GooglePlayRtdnEvent.id).where(GooglePlayRtdnEvent.message_id == message_id)
        )
        if dup.scalar_one_or_none() is not None:
            return {"ok": True, "duplicate": True}

    raw_data = message.get("data")
    if not raw_data:
        raise HTTPException(400, "data requerido")

    try:
        decoded = base64.b64decode(raw_data).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as exc:
        raise HTTPException(400, "data invalido") from exc

    sub_notif = payload.get("subscriptionNotification") or {}
    notification_type = sub_notif.get("notificationType")
    purchase_token = sub_notif.get("purchaseToken")
    subscription_id = sub_notif.get("subscriptionId")

    async with async_session_factory() as session:
        session.add(
            GooglePlayRtdnEvent(
                message_id=message_id,
                notification_type=notification_type,
                purchase_token=purchase_token,
                payload=payload,
                processed_at=datetime.utcnow(),
            )
        )
        await session.commit()

    if purchase_token and subscription_id:
        try:
            verified = await verify_subscription(purchase_token, subscription_id)
            from src.db.models import Suscripcion

            async with async_session_factory() as session:
                row = await session.execute(
                    select(Suscripcion.usuario_id).where(
                        Suscripcion.google_purchase_token == purchase_token
                    )
                )
                user_id = row.scalar_one_or_none()

            if user_id is not None:
                if notification_type in DEACTIVATE_TYPES or should_deactivate(
                    verified.subscription_state
                ):
                    await desactivar_plan_google(purchase_token)
                    await sync_usuario_plan_efectivo(user_id)
                elif notification_type in RENEW_TYPES and verified.is_active:
                    await _activate_from_verified(user_id, purchase_token, verified)
        except Exception:
            logger.exception(
                "RTDN processing failed type=%s token=%s",
                notification_type,
                (purchase_token or "")[:16],
            )

    return {"ok": True, "message_id": message_id}
