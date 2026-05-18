"""Decoradores para handlers de Telegram (gating por tier, etc)."""
from __future__ import annotations

import functools
import logging
from typing import Awaitable, Callable

from telegram import Update
from telegram.ext import ContextTypes

from src.db.models import PlanSuscripcion
from src.db.repository import es_plan_minimo, obtener_plan_actual

logger = logging.getLogger(__name__)

HandlerFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]

TIER_LABELS = {
    PlanSuscripcion.FREE: "Free",
    PlanSuscripcion.STARTER: "Starter ($5.000/mes)",
    PlanSuscripcion.PRO: "Pro ($14.990/mes)",
    PlanSuscripcion.ELITE: "Elite ($39.990/mes)",
    PlanSuscripcion.LIFETIME: "Lifetime ($399.000 unico)",
}


def requiere_tier(minimo: PlanSuscripcion) -> Callable[[HandlerFn], HandlerFn]:
    """Bloquea el handler si el usuario no tiene el tier minimo requerido."""

    def decorator(handler: HandlerFn) -> HandlerFn:
        @functools.wraps(handler)
        async def wrapper(
            update: Update, ctx: ContextTypes.DEFAULT_TYPE
        ) -> None:
            user = update.effective_user
            if user is None:
                return
            uid = user.id
            if await es_plan_minimo(uid, minimo):
                return await handler(update, ctx)
            actual = await obtener_plan_actual(uid)
            label_min = TIER_LABELS.get(minimo, minimo.value)
            label_actual = TIER_LABELS.get(actual, actual.value)
            mensaje = (
                f"Esta funcion requiere plan <b>{label_min}</b> o superior.\n"
                f"Plan actual: <b>{label_actual}</b>.\n\n"
                "Mejora tu plan con /pagar"
            )
            target = update.effective_message
            if target is not None:
                try:
                    await target.reply_text(mensaje)
                except Exception:
                    logger.exception("No pude enviar mensaje de upsell a uid=%s", uid)

        return wrapper

    return decorator
