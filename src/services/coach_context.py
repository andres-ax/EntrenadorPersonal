"""Construccion de prompt contextual para el coach."""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from src.cache import get_perfil_block as cache_get_perfil_block
from src.cache import set_perfil_block as cache_set_perfil_block
from src.db.repository import (
    obtener_compromiso_activo,
    obtener_o_crear_streak,
    obtener_o_crear_usuario,
)
from src.services.hidratacion import consumo_hoy_ml, objetivo_ml


async def build_coach_prompt(
    texto: str,
    uid: int,
    *,
    conversacion_titulo: str | None = None,
    conversacion_id: int | None = None,
    canal: str | None = None,
) -> str:
    """Prompt con perfil, tono, wearables, modo e historial del hilo activo."""
    cached_static = await cache_get_perfil_block(uid)
    user = await obtener_o_crear_usuario(uid)
    tz_name = user.timezone or "America/Bogota"
    try:
        ahora_user = datetime.now(ZoneInfo(tz_name))
    except Exception:
        tz_name = "America/Bogota"
        ahora_user = datetime.now(ZoneInfo(tz_name))
    hoy_user = ahora_user.date()

    agua_hoy = await consumo_hoy_ml(uid)
    agua_obj = await objetivo_ml(uid)

    dinamicos = [
        f"uid={uid}",
        f"fecha={hoy_user.isoformat()}",
        f"hora_actual={ahora_user.strftime('%H:%M')}",
        f"tz={tz_name}",
        f"tono={user.tono.value if user.tono else 'firme'}",
        f"pais={user.pais or 'CO'}",
        f"agua_hoy={agua_hoy}ml",
        f"agua_objetivo={agua_obj}ml",
    ]
    if conversacion_titulo:
        dinamicos.append(f"hilo='{conversacion_titulo[:80]}'")

    modo = "libre"
    if conversacion_id is not None and canal:
        from src.services.coach_modo import resolver_modo_coach

        modo = await resolver_modo_coach(uid, conversacion_id, canal)
    dinamicos.append(f"modo={modo}")

    if modo == "libre":
        from src.services.coach_historial_snapshot import build_historial_snapshot

        historial = await build_historial_snapshot(uid)
        if historial:
            dinamicos.append(f"historial_deportista=({historial})")

    from src.services.wearables import obtener_resumen_biometrico

    resumen_wearables = await obtener_resumen_biometrico(uid)
    if resumen_wearables:
        dinamicos.append(f"wearables_recientes=({resumen_wearables})")

    if cached_static is not None:
        return f"[{' | '.join(dinamicos)} | {cached_static}] {texto}"

    def _sanitize(v: str) -> str:
        return re.sub(r"[\[\]|{}<>]", "", v)[:80]

    estaticos = []
    if user.nombre:
        estaticos.append(f"nombre={_sanitize(user.nombre)}")
    if user.peso_kg:
        estaticos.append(f"peso={user.peso_kg}kg")
    if user.altura_cm:
        estaticos.append(f"altura={user.altura_cm}cm")
    if user.edad:
        estaticos.append(f"edad={user.edad}")
    if user.objetivo:
        estaticos.append(f"objetivo={_sanitize(user.objetivo)}")
    if user.nivel:
        estaticos.append(f"nivel={_sanitize(user.nivel)}")
    if user.dias_entreno:
        estaticos.append(f"dias_entreno={user.dias_entreno}")
    if user.deporte_principal:
        estaticos.append(f"deporte={_sanitize(user.deporte_principal)}")
    if user.categoria_deporte:
        estaticos.append(f"categoria_deporte={user.categoria_deporte.value}")
    if user.modalidad_deporte:
        estaticos.append(f"modalidad={_sanitize(user.modalidad_deporte)}")
    if user.es_competitivo:
        estaticos.append("competitivo=si")
    estaticos.append(f"onboarding={'si' if user.onboarding_completo else 'no'}")
    compromiso = await obtener_compromiso_activo(uid)
    if compromiso:
        estaticos.append(
            f"compromiso='{compromiso.objetivo_texto[:80]}' (deadline={compromiso.deadline.isoformat()})"
        )
    try:
        streak = await obtener_o_crear_streak(uid, "entreno")
        estaticos.append(f"streak_entreno={streak.dias_actuales}")
    except Exception:
        pass
    if user.pausado_hasta and user.pausado_hasta >= hoy_user:
        estaticos.append(f"pausado_hasta={user.pausado_hasta.isoformat()}")
    estatico_block = " | ".join(estaticos)
    await cache_set_perfil_block(uid, estatico_block)
    return f"[{' | '.join(dinamicos)} | {estatico_block}] {texto}"
