"""Panel deportista (server-side Jinja2 + HTMX + vanilla JS).

Auth: cookie HttpOnly `user_jwt`. Se setea desde TRES origenes posibles:
- /login/deportista con codigo de 6 digitos generado por /codigo_web en el bot.
- POST /api/auth/codigo (mismo flujo via JSON).
- POST /api/auth/initdata si el panel se abre desde Telegram Mini App.

Sin sesion -> redirect a /login.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from src.api.auth import verify_jwt
from src.db.connection import async_session_factory
from src.db.models import (
    Comida,
    Compromiso,
    MetricaCorporal,
    MetricaSueno,
    SesionEntrenamiento,
    Usuario,
)
from src.db.repository import (
    historial_peso,
    listar_prs,
    obtener_o_crear_streak,
    obtener_usuario,
    reporte_semanal,
    resumen_nutricional_dia,
)
from src.web.templates import render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app", tags=["panel-deportista"], include_in_schema=False)


USER_COOKIE_NAME = "user_jwt"


async def get_user_from_cookie(
    request: Request, user_jwt: str | None = Cookie(default=None, alias=USER_COOKIE_NAME)
) -> dict | None:
    """Devuelve dict {uid: int, perfil: Usuario|None} si la cookie es valida, sino None."""
    if not user_jwt:
        return None
    uid = verify_jwt(user_jwt)
    if uid is None:
        return None
    perfil = await obtener_usuario(uid)
    return {"uid": uid, "perfil": perfil}


def _redirect_login() -> RedirectResponse:
    return RedirectResponse(url="/login?tab=deportista", status_code=303)


@router.get("/", response_class=HTMLResponse)
async def app_root(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return _redirect_login()
    return RedirectResponse(url="/app/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    """KPIs del dia y semana del usuario, server-rendered."""
    if user is None:
        return _redirect_login()
    uid = user["uid"]
    reporte = await reporte_semanal(uid)
    streak = await obtener_o_crear_streak(uid, "entreno")
    nutricion = await resumen_nutricional_dia(uid)
    peso_hist = await historial_peso(uid, limit=5)
    return render(
        request,
        "app/dashboard.html",
        {
            "user": user,
            "active": "dashboard",
            "page_title": "Hoy",
            "page_subtitle": "Resumen del dia y la semana",
            "reporte": reporte,
            "streak": {
                "dias_actuales": streak.dias_actuales,
                "max_historico": streak.max_historico,
                "freezes_disponibles": streak.freezes_disponibles,
            },
            "nutricion": nutricion,
            "peso_recientes": [
                {"fecha": str(r.fecha), "peso_kg": r.peso_kg} for r in peso_hist
            ],
        },
    )


@router.get("/calendario", response_class=HTMLResponse)
async def calendario(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    """Calendario semanal: 7 dias con/sin entrenamientos."""
    if user is None:
        return _redirect_login()
    uid = user["uid"]
    hoy = date.today()
    inicio = hoy - timedelta(days=hoy.weekday())
    async with async_session_factory() as session:
        u_q = await session.execute(select(Usuario.id).where(Usuario.telegram_id == uid))
        usuario_id = u_q.scalar_one_or_none()
        sesiones = []
        if usuario_id:
            s_q = await session.execute(
                select(SesionEntrenamiento)
                .where(
                    SesionEntrenamiento.usuario_id == usuario_id,
                    SesionEntrenamiento.fecha >= inicio,
                    SesionEntrenamiento.fecha < inicio + timedelta(days=7),
                )
                .order_by(SesionEntrenamiento.fecha)
            )
            sesiones = list(s_q.scalars().all())
    by_fecha = {s.fecha: s for s in sesiones}
    dias = []
    nombres = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
    for i in range(7):
        f = inicio + timedelta(days=i)
        s = by_fecha.get(f)
        dias.append({
            "nombre": nombres[i],
            "fecha": f,
            "es_hoy": f == hoy,
            "realizado": s is not None,
            "tipo": s.tipo.value if s and s.tipo else None,
            "notas": s.notas if s and s.notas else "",
            "duracion_min": s.duracion_min if s else None,
        })
    return render(
        request,
        "app/calendario.html",
        {
            "user": user,
            "active": "calendario",
            "page_title": "Calendario semanal",
            "page_subtitle": f"Semana del {inicio.strftime('%d %b')} al {(inicio + timedelta(days=6)).strftime('%d %b %Y')}",
            "dias": dias,
            "semana_inicio": inicio,
        },
    )


@router.get("/plan", response_class=HTMLResponse)
async def plan(request: Request, user: dict | None = Depends(get_user_from_cookie)):
    if user is None:
        return _redirect_login()
    return render(
        request,
        "app/plan.html",
        {
            "user": user,
            "active": "plan",
            "page_title": "Plan semanal",
            "page_subtitle": "Tu rutina personalizada generada por el coach",
        },
    )


@router.get("/prs", response_class=HTMLResponse)
async def prs(request: Request, user: dict | None = Depends(get_user_from_cookie)):
    if user is None:
        return _redirect_login()
    uid = user["uid"]
    items = await listar_prs(uid)
    return render(
        request,
        "app/prs.html",
        {
            "user": user,
            "active": "prs",
            "page_title": "Personal Records",
            "page_subtitle": f"{len(items)} marcas registradas",
            "prs": items,
        },
    )


@router.get("/historial", response_class=HTMLResponse)
async def historial(
    request: Request,
    user: dict | None = Depends(get_user_from_cookie),
    tipo: str = "entrenos",
    dias: int = 30,
):
    """Historial completo: entrenos, comidas, sueno, peso."""
    if user is None:
        return _redirect_login()
    uid = user["uid"]
    desde = date.today() - timedelta(days=dias)
    items: list = []
    headers: list[str] = []
    async with async_session_factory() as session:
        u_q = await session.execute(select(Usuario.id).where(Usuario.telegram_id == uid))
        usuario_id = u_q.scalar_one_or_none()
        if usuario_id:
            if tipo == "entrenos":
                q = await session.execute(
                    select(SesionEntrenamiento)
                    .where(
                        SesionEntrenamiento.usuario_id == usuario_id,
                        SesionEntrenamiento.fecha >= desde,
                    )
                    .order_by(SesionEntrenamiento.fecha.desc())
                    .limit(100)
                )
                rows = list(q.scalars().all())
                headers = ["Fecha", "Tipo", "Duracion", "RPE", "Notas"]
                items = [
                    {
                        "Fecha": s.fecha.isoformat(),
                        "Tipo": s.tipo.value if s.tipo else "-",
                        "Duracion": f"{s.duracion_min} min" if s.duracion_min else "-",
                        "RPE": s.rpe_promedio if s.rpe_promedio is not None else "-",
                        "Notas": (s.notas or "")[:100],
                    }
                    for s in rows
                ]
            elif tipo == "comidas":
                q = await session.execute(
                    select(Comida)
                    .where(
                        Comida.usuario_id == usuario_id,
                        Comida.fecha >= desde,
                    )
                    .order_by(Comida.fecha.desc(), Comida.id.desc())
                    .limit(100)
                )
                rows = list(q.scalars().all())
                headers = ["Fecha", "Tipo", "Calorias", "Proteina", "Carbs", "Grasa"]
                items = [
                    {
                        "Fecha": c.fecha.isoformat(),
                        "Tipo": (c.tipo.value if c.tipo else "-"),
                        "Calorias": c.calorias or "-",
                        "Proteina": f"{c.proteinas_g}g" if c.proteinas_g else "-",
                        "Carbs": f"{c.carbohidratos_g}g" if c.carbohidratos_g else "-",
                        "Grasa": f"{c.grasas_g}g" if c.grasas_g else "-",
                    }
                    for c in rows
                ]
            elif tipo == "sueno":
                q = await session.execute(
                    select(MetricaSueno)
                    .where(
                        MetricaSueno.usuario_id == usuario_id,
                        MetricaSueno.fecha >= desde,
                    )
                    .order_by(MetricaSueno.fecha.desc())
                    .limit(100)
                )
                rows = list(q.scalars().all())
                headers = ["Fecha", "Horas", "Calidad", "Notas"]
                items = [
                    {
                        "Fecha": s.fecha.isoformat(),
                        "Horas": s.horas,
                        "Calidad": s.calidad if s.calidad else "-",
                        "Notas": (s.notas or "")[:80],
                    }
                    for s in rows
                ]
            elif tipo == "peso":
                q = await session.execute(
                    select(MetricaCorporal)
                    .where(
                        MetricaCorporal.usuario_id == usuario_id,
                        MetricaCorporal.fecha >= desde,
                    )
                    .order_by(MetricaCorporal.fecha.desc())
                    .limit(100)
                )
                rows = list(q.scalars().all())
                headers = ["Fecha", "Peso", "Grasa %", "Cintura"]
                items = [
                    {
                        "Fecha": m.fecha.isoformat(),
                        "Peso": f"{m.peso_kg} kg" if m.peso_kg else "-",
                        "Grasa %": f"{m.grasa_pct}%" if m.grasa_pct else "-",
                        "Cintura": f"{m.cintura_cm} cm" if m.cintura_cm else "-",
                    }
                    for m in rows
                ]
    return render(
        request,
        "app/historial.html",
        {
            "user": user,
            "active": "historial",
            "page_title": "Historial",
            "page_subtitle": f"Ultimos {dias} dias",
            "tipo": tipo,
            "dias": dias,
            "items": items,
            "headers": headers,
        },
    )


@router.get("/graficos", response_class=HTMLResponse)
async def graficos(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    """Vista de los 4 graficos PNG generados por matplotlib."""
    if user is None:
        return _redirect_login()
    return render(
        request,
        "app/graficos.html",
        {
            "user": user,
            "active": "graficos",
            "page_title": "Graficos de progreso",
            "page_subtitle": "Peso, volumen, macros y streak",
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_view(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return _redirect_login()
    uid = user["uid"]
    async with async_session_factory() as session:
        c_q = await session.execute(
            select(Compromiso)
            .join(Usuario, Compromiso.usuario_id == Usuario.id)
            .where(Usuario.telegram_id == uid, Compromiso.activo.is_(True))
            .order_by(Compromiso.fecha_firma.desc())
            .limit(1)
        )
        compromiso = c_q.scalar_one_or_none()
    return render(
        request,
        "app/settings.html",
        {
            "user": user,
            "active": "settings",
            "page_title": "Configuracion",
            "page_subtitle": "Tu perfil, compromiso y preferencias",
            "perfil": user.get("perfil"),
            "compromiso": compromiso,
        },
    )


@router.get("/pagar", response_class=HTMLResponse)
async def pagar(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    from src.config import settings

    if user is None:
        return _redirect_login()
    perfil = user.get("perfil")
    return render(
        request,
        "app/pagar.html",
        {
            "user": user,
            "active": "pagar",
            "page_title": "Plan y pagos",
            "page_subtitle": "Mejora tu cuenta o consulta tu plan actual",
            "plan_actual": perfil.plan_actual.value if perfil and perfil.plan_actual else "free",
            "plan_expira_en": perfil.plan_expira_en if perfil else None,
            "precios": {
                "starter": settings.precio_starter_cop,
                "pro": settings.precio_pro_cop,
                "elite": settings.precio_elite_cop,
                "lifetime": settings.precio_lifetime_cop,
            },
        },
    )


@router.get("/llamar", response_class=HTMLResponse)
async def llamar(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return _redirect_login()
    return render(
        request,
        "app/llamar.html",
        {
            "user": user,
            "active": "llamar",
            "page_title": "Llamar al coach",
            "page_subtitle": "Conversa con el coach IA por voz",
        },
    )


@router.get("/wearables", response_class=HTMLResponse)
async def wearables(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return _redirect_login()
    return render(
        request,
        "app/wearables.html",
        {
            "user": user,
            "active": "wearables",
            "page_title": "Wearables",
            "page_subtitle": "Conecta Whoop, Strava, Garmin o Google Fit",
        },
    )
