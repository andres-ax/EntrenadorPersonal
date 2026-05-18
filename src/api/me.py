"""Endpoints REST para el Mini App. Auth via JWT del initData."""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response

from src.api.auth import get_uid_from_token
from src.db.repository import (
    historial_peso,
    listar_prs,
    obtener_o_crear_streak,
    obtener_usuario,
    reporte_semanal,
    resumen_nutricional_dia,
)
from src.services.charts import (
    chart_macros_dia,
    chart_peso,
    chart_streak_calendario,
    chart_volumen_semanal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("/perfil")
async def perfil(uid: int = Depends(get_uid_from_token)) -> dict:
    u = await obtener_usuario(uid)
    if u is None:
        raise HTTPException(404, "Usuario no encontrado")
    return {
        "telegram_id": u.telegram_id,
        "nombre": u.nombre,
        "edad": u.edad,
        "peso_kg": u.peso_kg,
        "altura_cm": u.altura_cm,
        "objetivo": u.objetivo,
        "nivel": u.nivel,
        "deporte_principal": u.deporte_principal,
        "tono": u.tono.value if u.tono else "firme",
        "onboarding_completo": u.onboarding_completo,
    }


@router.get("/dashboard")
async def dashboard(uid: int = Depends(get_uid_from_token)) -> dict:
    reporte = await reporte_semanal(uid)
    streak = await obtener_o_crear_streak(uid, "entreno")
    nutricion = await resumen_nutricional_dia(uid)
    historial = await historial_peso(uid, limit=10)
    return {
        "reporte_semanal": reporte,
        "streak_entreno": {
            "dias_actuales": streak.dias_actuales,
            "max_historico": streak.max_historico,
            "freezes_disponibles": streak.freezes_disponibles,
        },
        "nutricion_hoy": nutricion,
        "peso_recientes": [
            {"fecha": str(r.fecha), "peso_kg": r.peso_kg} for r in historial
        ],
    }


@router.get("/prs")
async def prs(uid: int = Depends(get_uid_from_token)) -> dict:
    items = await listar_prs(uid)
    return {
        "prs": [
            {"ejercicio": p.ejercicio, "peso_kg": p.peso_kg, "reps": p.reps}
            for p in items
        ]
    }


@router.get("/charts/peso.png")
async def chart_peso_png(uid: int = Depends(get_uid_from_token)) -> Response:
    img = await chart_peso(uid)
    if img is None:
        raise HTTPException(204)
    return Response(content=img.getvalue(), media_type="image/png")


@router.get("/charts/volumen.png")
async def chart_volumen_png(uid: int = Depends(get_uid_from_token)) -> Response:
    img = await chart_volumen_semanal(uid)
    if img is None:
        raise HTTPException(204)
    return Response(content=img.getvalue(), media_type="image/png")


@router.get("/charts/macros.png")
async def chart_macros_png(
    uid: int = Depends(get_uid_from_token), fecha: str | None = None
) -> Response:
    fecha_obj = date.fromisoformat(fecha) if fecha else None
    img = await chart_macros_dia(uid, fecha_obj)
    if img is None:
        raise HTTPException(204)
    return Response(content=img.getvalue(), media_type="image/png")


@router.get("/charts/streak.png")
async def chart_streak_png(uid: int = Depends(get_uid_from_token)) -> Response:
    img = await chart_streak_calendario(uid)
    if img is None:
        raise HTTPException(204)
    return Response(content=img.getvalue(), media_type="image/png")
