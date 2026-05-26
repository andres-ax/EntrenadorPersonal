"""Verificacion server-side de suscripciones Google Play."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from src.config import settings
from src.services.google_play_products import is_valid_product_id, product_to_plan

logger = logging.getLogger(__name__)

ACTIVE_STATES = {
    "SUBSCRIPTION_STATE_ACTIVE",
    "SUBSCRIPTION_STATE_IN_GRACE_PERIOD",
}

INACTIVE_STATES = {
    "SUBSCRIPTION_STATE_EXPIRED",
    "SUBSCRIPTION_STATE_REVOKED",
    "SUBSCRIPTION_STATE_ON_HOLD",
    "SUBSCRIPTION_STATE_PAUSED",
}


@dataclass(frozen=True)
class VerifiedPurchase:
    is_active: bool
    product_id: str
    order_id: str | None
    base_plan_id: str | None
    linked_purchase_token: str | None
    expira_en: datetime | None
    subscription_state: str | None


def _parse_rfc3339(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.replace(tzinfo=None)
    except ValueError:
        logger.warning("expiryTime invalido: %s", value)
        return None


def _dev_verify(purchase_token: str, product_id: str) -> VerifiedPurchase:
    """Modo desarrollo/test: tokens con prefijo dev_."""
    if not purchase_token.startswith("dev_"):
        raise ValueError("Token dev invalido")
    if not is_valid_product_id(product_id):
        raise ValueError(f"product_id desconocido: {product_id}")
    _, duracion = product_to_plan(product_id)
    days = 365 if duracion.value == "anual" else 30
    expira = datetime.utcnow() + timedelta(days=days)
    return VerifiedPurchase(
        is_active=True,
        product_id=product_id,
        order_id=f"dev-order-{purchase_token[-8:]}",
        base_plan_id=duracion.value,
        linked_purchase_token=None,
        expira_en=expira,
        subscription_state="SUBSCRIPTION_STATE_ACTIVE",
    )


def _build_android_publisher():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    raw = settings.google_play_service_account_json
    if not raw:
        raise RuntimeError("google_play_service_account_json no configurado")
    info = json.loads(raw)
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=["https://www.googleapis.com/auth/androidpublisher"],
    )
    return build("androidpublisher", "v3", credentials=credentials, cache_discovery=False)


def _parse_google_subscription_v2(data: dict[str, Any], product_id: str) -> VerifiedPurchase:
    state = data.get("subscriptionState")
    line_items = data.get("lineItems") or []
    line = line_items[0] if line_items else {}
    expiry = _parse_rfc3339(line.get("expiryTime"))
    return VerifiedPurchase(
        is_active=state in ACTIVE_STATES,
        product_id=product_id,
        order_id=data.get("latestOrderId"),
        base_plan_id=line.get("offerDetails", {}).get("basePlanId"),
        linked_purchase_token=data.get("linkedPurchaseToken"),
        expira_en=expiry,
        subscription_state=state,
    )


async def verify_subscription(purchase_token: str, product_id: str) -> VerifiedPurchase:
    """Verifica purchase_token con Google o modo dev."""
    if not is_valid_product_id(product_id):
        raise ValueError(f"product_id desconocido: {product_id}")

    if not settings.google_play_billing_enabled:
        if settings.env in ("dev", "test") and purchase_token.startswith("dev_"):
            return _dev_verify(purchase_token, product_id)
        raise RuntimeError("Google Play Billing deshabilitado")

    service = _build_android_publisher()
    package_name = settings.google_play_package_name
    data = (
        service.purchases()
        .subscriptionsv2()
        .get(packageName=package_name, token=purchase_token)
        .execute()
    )
    verified = _parse_google_subscription_v2(data, product_id)
    if verified.product_id != product_id:
        # lineItems pueden traer productId distinto en upgrades; confiar en request
        verified = VerifiedPurchase(
            is_active=verified.is_active,
            product_id=product_id,
            order_id=verified.order_id,
            base_plan_id=verified.base_plan_id,
            linked_purchase_token=verified.linked_purchase_token,
            expira_en=verified.expira_en,
            subscription_state=verified.subscription_state,
        )
    return verified


def should_deactivate(state: str | None) -> bool:
    return state in INACTIVE_STATES
