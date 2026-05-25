"""Endpoints publicos sin auth para la landing y stats agregados.

Rate-limited en memoria simple para evitar abuso.
"""

from __future__ import annotations

import logging
import time as _t
from collections import defaultdict, deque
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import (
    Comida,
    DeporteCatalogo,
    EventoBot,
    PersonalRecord,
    PlanSuscripcion,
    SesionEntrenamiento,
    Streak,
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
        total_usuarios = (await session.execute(select(func.count(Usuario.id)))).scalar() or 0
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
        sesiones_totales = (
            await session.execute(select(func.count(SesionEntrenamiento.id)))
        ).scalar() or 0
        comidas_totales = (await session.execute(select(func.count(Comida.id)))).scalar() or 0
        prs_totales = (await session.execute(select(func.count(PersonalRecord.id)))).scalar() or 0
        interacciones_totales = (
            await session.execute(select(func.count(EventoBot.id)))
        ).scalar() or 0
        paises_distintos = (
            await session.execute(
                select(func.count(func.distinct(Usuario.pais))).where(Usuario.pais.isnot(None))
            )
        ).scalar() or 0
        racha_max = (await session.execute(select(func.max(Streak.max_historico)))).scalar() or 0
        deportes_count = (
            await session.execute(select(func.count(DeporteCatalogo.id)))
        ).scalar() or 0
        paises_q = await session.execute(
            select(Usuario.pais, func.count(Usuario.id))
            .group_by(Usuario.pais)
            .order_by(func.count(Usuario.id).desc())
            .limit(5)
        )
        paises_top = [{"pais": pais or "??", "n": cnt} for pais, cnt in paises_q]

    data = {
        "usuarios_totales": total_usuarios,
        "usuarios_activos": onboarded,
        "sesiones_registradas_30d": sesiones_30d,
        "sesiones_totales": sesiones_totales,
        "comidas_registradas": comidas_totales,
        "prs_registrados": prs_totales,
        "interacciones_totales": interacciones_totales,
        "paises_count": paises_distintos,
        "racha_max_global": racha_max,
        "deportes_count": deportes_count or 71,
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

    # Resend newsletter deshabilitado: no tenemos audience ID configurado.
    # El email queda guardado en la tabla eventos_bot para exportar manualmente.
    # Cuando se configure RESEND_API_KEY + un audience en Resend, reactivar aqui.

    return {"ok": True, "ya_inscrito": False}


# --- Chat demo (widget landing) ---


class ChatDemoReq(BaseModel):
    mensaje: str
    session_id: str | None = None


@router.post("/chat-demo")
async def chat_demo_endpoint(req: ChatDemoReq, request: Request) -> dict:
    """Widget de chat demo en la landing. Rate limited por IP."""
    ip = request.client.host if request.client else "unknown"
    if not _check_rate_limit(f"chat_demo:{ip}", limit=10):
        raise HTTPException(429, "Demasiados mensajes. Espera un momento.")
    if not req.mensaje or not req.mensaje.strip():
        raise HTTPException(400, "Mensaje vacio")
    if len(req.mensaje) > 500:
        raise HTTPException(400, "Mensaje muy largo (max 500 chars)")

    from src.services.chat_demo import chat_demo

    result = await chat_demo(req.session_id, req.mensaje.strip())
    return result


@router.get("/precios")
async def precios_publicos() -> dict:
    """Precios actuales por tier para que la landing los muestre dinamicamente."""
    from src.db.models import DuracionPago
    from src.services.pricing import descripcion_plan, formatear_precio, precio_cop

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
