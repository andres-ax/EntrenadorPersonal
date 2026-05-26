"""Resolucion de modo coach: onboarding Telegram vs libre."""
from __future__ import annotations

from typing import Literal

from src.db.repository import obtener_o_crear_usuario
from src.services.conversation_service import obtener_conversacion_por_id

CoachModo = Literal["onboarding_telegram", "libre"]


async def resolver_modo_coach(
    telegram_id: int,
    conversacion_id: int,
    canal: str,
) -> CoachModo:
    user = await obtener_o_crear_usuario(telegram_id)
    conv = await obtener_conversacion_por_id(conversacion_id)
    if conv is None:
        return "libre"
    if canal == "telegram" and conv.es_principal and not user.onboarding_completo:
        return "onboarding_telegram"
    return "libre"
