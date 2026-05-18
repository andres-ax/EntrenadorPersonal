"""Endpoints publicos sin auth para la landing y stats agregados.

Rate-limited en memoria simple para evitar abuso.
"""
from __future__ import annotations

import logging
import time as _t
from collections import defaultdict, deque
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import (
    EventoBot,
    PlanSuscripcion,
    SesionEntrenamiento,
    Usuario,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["public"])

_rate_buckets: dict[str, deque] = defaultdict(deque)
_RATE_LIMIT_PER_MIN = 10


def _check_rate_limit(key: str, limit: int = _RATE_LIMIT_PER_MIN) -> bool:
    ahora = _t.time()
    cutoff = ahora - 60
    bucket = _rate_buckets[key]
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(ahora)
    return True


_CACHE_STATS = {"ts": 0.0, "data": {}}


@router.get("/stats")
async def stats_publicas() -> dict:
    """Stats agregadas para mostrar social proof en la landing. Cache 1h."""
    ahora = _t.time()
    if (ahora - _CACHE_STATS["ts"]) < 3600 and _CACHE_STATS["data"]:
        return _CACHE_STATS["data"]

    async with async_session_factory() as session:
        total_usuarios = (
            await session.execute(select(func.count(Usuario.id)))
        ).scalar() or 0
        onboarded = (
            await session.execute(
                select(func.count(Usuario.id)).where(
                    Usuario.onboarding_completo == True  # noqa: E712
                )
            )
        ).scalar() or 0
        hace_30 = datetime.utcnow() - timedelta(days=30)
        sesiones_30d = (
            await session.execute(
                select(func.count(SesionEntrenamiento.id)).where(
                    SesionEntrenamiento.created_at >= hace_30
                )
            )
        ).scalar() or 0
        paises_q = await session.execute(
            select(Usuario.pais, func.count(Usuario.id))
            .group_by(Usuario.pais)
            .order_by(func.count(Usuario.id).desc())
            .limit(5)
        )
        paises_top = [
            {"pais": pais or "??", "n": cnt} for pais, cnt in paises_q
        ]

    data = {
        "usuarios_totales": total_usuarios,
        "usuarios_activos": onboarded,
        "sesiones_registradas_30d": sesiones_30d,
        "paises_top": paises_top,
        "actualizado_en": datetime.utcnow().isoformat(),
    }
    _CACHE_STATS["ts"] = ahora
    _CACHE_STATS["data"] = data
    return data


class NewsletterReq(BaseModel):
    email: EmailStr
    fuente: str = "landing"


@router.post("/newsletter")
async def newsletter_signup(req: NewsletterReq, request: Request) -> dict:
    """Captura email para newsletter. Resend si esta configurado, sino log."""
    ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"newsletter:{ip}", limit=5):
        raise HTTPException(429, "Demasiados intentos, espera un momento")

    async with async_session_factory() as session:
        existente = await session.execute(
            select(EventoBot).where(
                EventoBot.tipo_evento == "newsletter_signup",
                EventoBot.payload["email"].astext == req.email,
            )
        )
        if existente.scalar_one_or_none() is not None:
            return {"ok": True, "ya_inscrito": True}
        evento = EventoBot(
            usuario_id=None,
            tipo_evento="newsletter_signup",
            payload={"email": req.email, "fuente": req.fuente, "ip": ip},
        )
        session.add(evento)
        await session.commit()

    if settings.resend_api_key:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    "https://api.resend.com/audiences/{}/contacts".format(
                        settings.plausible_domain or "default"
                    ),
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={"email": req.email},
                )
        except Exception:
            logger.warning("No pude registrar email en Resend (audience inexistente o key invalida)")

    return {"ok": True, "ya_inscrito": False}


@router.get("/precios")
async def precios_publicos() -> dict:
    """Precios actuales por tier para que la landing los muestre dinamicamente."""
    from src.db.models import DuracionPago
    from src.services.pricing import (
        descripcion_plan,
        formatear_precio,
        precio_cop,
    )

    planes = []
    for plan in [
        PlanSuscripcion.FREE,
        PlanSuscripcion.STARTER,
        PlanSuscripcion.PRO,
        PlanSuscripcion.ELITE,
        PlanSuscripcion.LIFETIME,
    ]:
        if plan == PlanSuscripcion.LIFETIME:
            mensual = 0
            anual = 0
            lifetime = precio_cop(plan, DuracionPago.LIFETIME)
        else:
            mensual = precio_cop(plan, DuracionPago.MENSUAL)
            anual = precio_cop(plan, DuracionPago.ANUAL)
            lifetime = 0
        planes.append(
            {
                "plan": plan.value,
                "mensual_cop": mensual,
                "mensual_formato": formatear_precio(mensual),
                "anual_cop": anual,
                "anual_formato": formatear_precio(anual) if anual else None,
                "lifetime_cop": lifetime,
                "lifetime_formato": formatear_precio(lifetime) if lifetime else None,
                "descripcion": descripcion_plan(plan),
            }
        )
    return {
        "planes": planes,
        "descuento_anual_pct": settings.descuento_anual_pct,
        "cupos_lifetime_total": settings.cupos_lifetime_total,
    }
