"""Calculo de precios y duraciones por tier.

Lee precios desde Settings (override via env vars) y aplica descuento anual.
"""
from __future__ import annotations

import logging

from src.config import settings
from src.db.models import DuracionPago, PlanSuscripcion

logger = logging.getLogger(__name__)

DIAS_POR_DURACION = {
    DuracionPago.MENSUAL: 30,
    DuracionPago.ANUAL: 365,
    DuracionPago.LIFETIME: 36500,
}


def precio_cop(plan: PlanSuscripcion, duracion: DuracionPago) -> int:
    """Devuelve el monto esperado en pesos colombianos."""
    monto = _precio_cop_inner(plan, duracion)
    logger.debug(
        "precio_cop plan=%s duracion=%s -> %s COP",
        getattr(plan, "value", plan),
        getattr(duracion, "value", duracion),
        monto,
    )
    return monto


def _precio_cop_inner(plan: PlanSuscripcion, duracion: DuracionPago) -> int:
    if plan == PlanSuscripcion.FREE:
        return 0
    if plan == PlanSuscripcion.LIFETIME:
        return settings.precio_lifetime_cop
    if duracion == DuracionPago.LIFETIME:
        return settings.precio_lifetime_cop

    base_mensual = {
        PlanSuscripcion.STARTER: settings.precio_starter_cop,
        PlanSuscripcion.PRO: settings.precio_pro_cop,
        PlanSuscripcion.ELITE: settings.precio_elite_cop,
    }.get(plan, 0)

    if duracion == DuracionPago.ANUAL:
        anual_sin_descuento = base_mensual * 12
        descuento = anual_sin_descuento * settings.descuento_anual_pct // 100
        return anual_sin_descuento - descuento
    return base_mensual


def dias_duracion(plan: PlanSuscripcion, duracion: DuracionPago) -> int:
    if plan == PlanSuscripcion.LIFETIME or duracion == DuracionPago.LIFETIME:
        return 36500
    return DIAS_POR_DURACION.get(duracion, 30)


def formatear_precio(monto_cop: int) -> str:
    """Formatea 14990 -> '$14.990'."""
    return f"${monto_cop:,.0f}".replace(",", ".")


def descripcion_plan(plan: PlanSuscripcion) -> str:
    """Descripcion corta de cada plan para UI."""
    return {
        PlanSuscripcion.FREE: "Acceso basico: bot conversacional, escalation diario, 1 foto comida/dia.",
        PlanSuscripcion.STARTER: "Charts avanzados, photo ilimitado, Mini App, 5min Realtime trial.",
        PlanSuscripcion.PRO: "Todo Starter + voz coach, 30min Realtime, 1 wearable, plan generator.",
        PlanSuscripcion.ELITE: "Todo Pro + 120min Realtime, wearables ilimitados, PDFs ilimitados.",
        PlanSuscripcion.LIFETIME: "Elite para siempre. Sin renovacion. Solo 100 cupos en launch.",
    }.get(plan, "")
