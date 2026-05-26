"""IDs de producto Google Play y mapeo a planes EntrenadorAX."""
from __future__ import annotations

from dataclasses import dataclass

from src.db.models import DuracionPago, PlanSuscripcion
from src.services.pricing import descripcion_plan, formatear_precio, precio_cop

PRO_MENSUAL = "pro_mensual"
PRO_ANUAL = "pro_anual"
ELITE_MENSUAL = "elite_mensual"
ELITE_ANUAL = "elite_anual"

ALL_PRODUCT_IDS: tuple[str, ...] = (
    PRO_MENSUAL,
    PRO_ANUAL,
    ELITE_MENSUAL,
    ELITE_ANUAL,
)

PRODUCT_TO_PLAN: dict[str, tuple[PlanSuscripcion, DuracionPago]] = {
    PRO_MENSUAL: (PlanSuscripcion.PRO, DuracionPago.MENSUAL),
    PRO_ANUAL: (PlanSuscripcion.PRO, DuracionPago.ANUAL),
    ELITE_MENSUAL: (PlanSuscripcion.ELITE, DuracionPago.MENSUAL),
    ELITE_ANUAL: (PlanSuscripcion.ELITE, DuracionPago.ANUAL),
}

PLAN_FEATURES_UI: dict[PlanSuscripcion, list[str]] = {
    PlanSuscripcion.PRO: [
        "Voz del coach en mensajes intensos",
        "Photo meal feedback ilimitado",
        "Charts avanzados y export CSV",
        "Plan generator semanal",
        "30 min Realtime al mes",
    ],
    PlanSuscripcion.ELITE: [
        "Todo Pro incluido",
        "120 min Realtime al mes",
        "Wearables ilimitados",
        "PDFs ilimitados",
        "Soporte prioritario y beta features",
    ],
}


def product_to_plan(product_id: str) -> tuple[PlanSuscripcion, DuracionPago]:
    mapped = PRODUCT_TO_PLAN.get(product_id)
    if mapped is None:
        raise ValueError(f"product_id desconocido: {product_id}")
    return mapped


def is_valid_product_id(product_id: str) -> bool:
    return product_id in PRODUCT_TO_PLAN


@dataclass(frozen=True)
class BillingPlanOffer:
    product_id: str
    plan: str
    duracion: str
    precio_cop_referencia: int
    precio_cop_formato: str
    descripcion: str
    features: list[str]
    popular: bool = False


def list_billing_offers() -> list[BillingPlanOffer]:
    """Ofertas para GET /api/me/billing/planes (precio COP es referencia web)."""
    offers: list[BillingPlanOffer] = []
    for product_id, (plan, duracion) in PRODUCT_TO_PLAN.items():
        cop = precio_cop(plan, duracion)
        offers.append(
            BillingPlanOffer(
                product_id=product_id,
                plan=plan.value,
                duracion=duracion.value,
                precio_cop_referencia=cop,
                precio_cop_formato=formatear_precio(cop),
                descripcion=descripcion_plan(plan),
                features=PLAN_FEATURES_UI.get(plan, []),
                popular=plan == PlanSuscripcion.PRO and duracion == DuracionPago.MENSUAL,
            )
        )
    return offers
