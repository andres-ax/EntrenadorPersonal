"""Endpoints REST para el Mini App. Auth via JWT del initData."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import func, select

from src.api.auth import get_uid_from_token
from src.db.connection import async_session_factory
from src.db.models import (
    Comida,
    MetricaCorporal,
    MetricaSueno,
    SesionEntrenamiento,
    Usuario,
)
from src.db.repository import (
    actualizar_usuario,
    guardar_comida,
    guardar_metrica_corporal,
    guardar_sesion,
    guardar_sueno,
    historial_peso,
    listar_prs,
    obtener_o_crear_streak,
    obtener_usuario,
    reporte_semanal,
    resumen_nutricional_dia,
    set_quiet_hours,
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


# --- Calendario semanal ---


@router.get("/calendar")
async def calendario(
    uid: int = Depends(get_uid_from_token), semana: str | None = None
) -> dict:
    """Devuelve los 7 dias de la semana con entrenos realizados."""
    inicio = date.today() - timedelta(days=date.today().weekday())
    if semana:
        try:
            ano, num = semana.split("-W")
            ano_i = int(ano)
            num_i = int(num)
            inicio = date.fromisocalendar(ano_i, num_i, 1)
        except (ValueError, IndexError):
            pass

    async with async_session_factory() as session:
        usuario_q = await session.execute(
            select(Usuario.id).where(Usuario.telegram_id == uid)
        )
        usuario_id = usuario_q.scalar_one_or_none()
        if usuario_id is None:
            raise HTTPException(404, "Usuario no encontrado")
        sesiones_q = await session.execute(
            select(SesionEntrenamiento).where(
                SesionEntrenamiento.usuario_id == usuario_id,
                SesionEntrenamiento.fecha >= inicio,
                SesionEntrenamiento.fecha < inicio + timedelta(days=7),
            )
        )
        sesiones = list(sesiones_q.scalars().all())
        by_fecha = {s.fecha: s for s in sesiones}

    dias = []
    for i in range(7):
        f = inicio + timedelta(days=i)
        s = by_fecha.get(f)
        dias.append(
            {
                "fecha": f.isoformat(),
                "realizado": s is not None,
                "planeado": False,
                "tipo": s.tipo.value if s and s.tipo else None,
                "resumen": s.notas if s and s.notas else "",
            }
        )
    return {"semana_inicio": inicio.isoformat(), "dias": dias}


# --- Logs (Mini App envia datos al bot) ---


class LogEntrenoReq(BaseModel):
    fecha: str
    tipo: str = "fuerza"
    duracion_min: int = 60
    ejercicios: list[dict] = []
    rpe: float | None = None
    notas: str = ""


@router.post("/log/entreno")
async def log_entreno(
    req: LogEntrenoReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    try:
        sesion = await guardar_sesion(
            telegram_id=uid,
            fecha_str=req.fecha,
            tipo=req.tipo,
            ejercicios=req.ejercicios,
            duracion_min=req.duracion_min,
            rpe=req.rpe,
            notas=req.notas,
        )
        return {"ok": True, "sesion_id": sesion.id}
    except Exception:
        logger.exception("Error log_entreno uid=%s", uid)
        raise HTTPException(400, "Error registrando entreno")


class LogPesoReq(BaseModel):
    peso_kg: float
    grasa_pct: float | None = None
    cintura_cm: float | None = None


@router.post("/log/peso")
async def log_peso(
    req: LogPesoReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    m = await guardar_metrica_corporal(
        telegram_id=uid,
        peso_kg=req.peso_kg,
        grasa_pct=req.grasa_pct,
        cintura_cm=req.cintura_cm,
    )
    return {"ok": True, "id": m.id}


class LogComidaReq(BaseModel):
    fecha: str
    tipo: str = "almuerzo"
    alimentos: list[str]
    calorias: int = 0
    proteinas: float = 0
    carbs: float = 0
    grasas: float = 0


@router.post("/log/comida")
async def log_comida(
    req: LogComidaReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    c = await guardar_comida(
        telegram_id=uid,
        fecha_str=req.fecha,
        tipo=req.tipo,
        alimentos=req.alimentos,
        calorias=req.calorias,
        proteinas=req.proteinas,
        carbs=req.carbs,
        grasas=req.grasas,
    )
    return {"ok": True, "id": c.id}


class LogSuenoReq(BaseModel):
    fecha: str
    horas: float
    calidad: int
    notas: str = ""


@router.post("/log/sueno")
async def log_sueno(
    req: LogSuenoReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    s = await guardar_sueno(
        telegram_id=uid,
        fecha_str=req.fecha,
        horas=req.horas,
        calidad=req.calidad,
        notas=req.notas,
    )
    return {"ok": True, "id": s.id}


# --- Settings ---


class SettingsPatchReq(BaseModel):
    tono: str | None = None
    idioma: str | None = None
    pais: str | None = None
    quiet_hours_inicio: str | None = None
    quiet_hours_fin: str | None = None


@router.get("/settings")
async def get_settings(uid: int = Depends(get_uid_from_token)) -> dict:
    u = await obtener_usuario(uid)
    if u is None:
        raise HTTPException(404)
    return {
        "tono": u.tono.value if u.tono else "firme",
        "idioma": u.idioma,
        "pais": u.pais,
        "quiet_hours_inicio": (
            u.quiet_hours_inicio.strftime("%H:%M") if u.quiet_hours_inicio else "22:00"
        ),
        "quiet_hours_fin": (
            u.quiet_hours_fin.strftime("%H:%M") if u.quiet_hours_fin else "07:00"
        ),
        "plan_actual": u.plan_actual.value if u.plan_actual else "free",
        "plan_expira_en": u.plan_expira_en.isoformat() if u.plan_expira_en else None,
    }


@router.patch("/settings")
async def patch_settings(
    req: SettingsPatchReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    from src.db.models import TonoCoach

    updates = {}
    if req.tono:
        try:
            updates["tono"] = TonoCoach(req.tono)
        except ValueError:
            raise HTTPException(400, "tono invalido")
    if req.idioma:
        updates["idioma"] = req.idioma[:8]
    if req.pais:
        updates["pais"] = req.pais[:8]
    if updates:
        await actualizar_usuario(uid, **updates)
    if req.quiet_hours_inicio and req.quiet_hours_fin:
        try:
            await set_quiet_hours(uid, req.quiet_hours_inicio, req.quiet_hours_fin)
        except Exception:
            raise HTTPException(400, "quiet_hours invalidas")
    return {"ok": True}


# --- Plan generator stub (real impl en Fase 7) ---


@router.post("/plan/generar")
async def generar_plan(uid: int = Depends(get_uid_from_token)) -> dict:
    """Genera plan semanal con LLM. Requiere Pro o superior."""
    from src.db.models import PlanSuscripcion
    from src.db.repository import es_plan_minimo

    if not await es_plan_minimo(uid, PlanSuscripcion.PRO):
        raise HTTPException(
            402, "Requiere plan Pro o superior. Mejora con /pagar en el bot."
        )
    from src.services.plan_generator import generar_plan_semanal_para

    plan = await generar_plan_semanal_para(uid)
    return {"plan": plan}


# --- Wearables (impl real en Fase 6, devuelve estructura vacia por ahora) ---


@router.get("/wearables")
async def listar_wearables(uid: int = Depends(get_uid_from_token)) -> dict:
    from src.services.wearables import listar_para_usuario, PROVEEDORES_DISPONIBLES

    items = await listar_para_usuario(uid)
    return {
        "integraciones": items,
        "proveedores_disponibles": PROVEEDORES_DISPONIBLES,
    }


@router.post("/wearables/{proveedor}/connect")
async def connect_wearable(
    proveedor: str, uid: int = Depends(get_uid_from_token)
) -> dict:
    from src.services.wearables import construir_url_oauth

    url = await construir_url_oauth(uid, proveedor)
    return {"url": url}


@router.post("/wearables/{proveedor}/sync")
async def sync_wearable(
    proveedor: str, uid: int = Depends(get_uid_from_token)
) -> dict:
    from src.services.wearables import sync_proveedor

    n = await sync_proveedor(uid, proveedor)
    return {"ok": True, "items_sincronizados": n}
