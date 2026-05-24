"""Rutas HTML del panel admin (server-side rendered, Jinja2 + HTMX).

Reemplaza completo el frontend Next.js que estaba en `frontend/admin/`.

Patrones:
- `/admin/login` + `POST /admin/login` -> setea cookie HttpOnly `admin_jwt`.
- `/admin/logout` -> borra la cookie.
- Resto de rutas usan `Depends(get_admin_from_cookie)` que redirige a /admin/login
  si no hay sesion.
- Llamamos directo las funciones del router JSON existente (`src/api/admin.py`)
  para no duplicar logica de DB. Esas funciones tienen `admin: dict = Depends(get_admin_from_token)`
  pero como aqui ya validamos el JWT desde cookie, podemos invocarlas con
  un dict `admin` valido.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import Date, cast, func, select

from src.api import admin as admin_api
from src.api.admin_auth import (
    ADMIN_COOKIE_NAME,
    ADMIN_JWT_TTL,
    LoginRequest,
    autenticar_admin,
    get_admin_from_cookie,
    get_admin_optional,
    require_super,
    sign_admin_jwt,
)
from src.web.templates import render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-ui"], include_in_schema=False)


# -----------------------------------------------------------------------------
# Login / logout
# -----------------------------------------------------------------------------


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request, admin: dict | None = Depends(get_admin_optional)
):
    if admin:
        return RedirectResponse(url="/admin/", status_code=303)
    return render(request, "admin/login.html", {"error": None})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    try:
        resp_login = await autenticar_admin(LoginRequest(email=email, password=password))
    except HTTPException as exc:
        return render(
            request,
            "admin/login.html",
            {"error": exc.detail, "email_prefill": email},
        )
    # Cookie HttpOnly Secure SameSite=Lax (para que sobreviva navegacion normal
    # pero NO se mande en cross-site POST request -> CSRF mitigado).
    response = RedirectResponse(url="/admin/", status_code=303)
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=resp_login.jwt,
        max_age=ADMIN_JWT_TTL,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    logger.info("admin_login_ok email=%s ip=%s", email, request.client.host if request.client else "?")
    return response


@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
    return response


# -----------------------------------------------------------------------------
# Dashboard
# -----------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request, admin: dict = Depends(get_admin_from_cookie)
):
    # Llama a finanzas() directamente (es una funcion async dentro de admin_api)
    finanzas_data = await admin_api.finanzas(admin=admin, dias=30)
    pagos_pendientes = await admin_api.listar_pagos(admin=admin, estado="pendiente_humano", limit=5)
    crisis_recientes = await admin_api.listar_crisis(admin=admin, nivel=None, dias=7, limit=5)
    return render(
        request,
        "admin/dashboard.html",
        {
            "admin": admin,
            "finanzas": finanzas_data,
            "pagos_pendientes": pagos_pendientes,
            "crisis_recientes": crisis_recientes,
            "active": "dashboard",
        },
    )


# -----------------------------------------------------------------------------
# Usuarios
# -----------------------------------------------------------------------------


@router.get("/usuarios", response_class=HTMLResponse)
async def usuarios_lista(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    q: str = "",
    plan: Optional[str] = None,
    pais: Optional[str] = None,
    bloqueado: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    data = await admin_api.listar_usuarios(
        admin=admin, q=q, plan=plan, pais=pais, bloqueado=bloqueado, limit=limit, offset=offset
    )
    template = "admin/_usuarios_tabla.html" if request.headers.get("hx-request") else "admin/usuarios.html"
    return render(
        request,
        template,
        {
            "admin": admin,
            "data": data,
            "filtros": {"q": q, "plan": plan, "pais": pais, "bloqueado": bloqueado, "limit": limit, "offset": offset},
            "active": "usuarios",
        },
    )


@router.get("/usuarios/{uid}", response_class=HTMLResponse)
async def usuario_detalle(
    uid: int, request: Request, admin: dict = Depends(get_admin_from_cookie)
):
    data = await admin_api.detalle_usuario(uid=uid, admin=admin)
    return render(
        request,
        "admin/usuario_detalle.html",
        {"admin": admin, "data": data, "uid": uid, "active": "usuarios"},
    )


@router.post("/usuarios/{uid}/asignar_plan_form")
async def asignar_plan_form(
    uid: int,
    admin: dict = Depends(get_admin_from_cookie),
    plan: str = Form(...),
    dias: int = Form(30),
):
    await admin_api.asignar_plan_manual(
        uid=uid, req=admin_api.AsignarPlanReq(plan=plan, dias=dias), admin=admin
    )
    return RedirectResponse(url=f"/admin/usuarios/{uid}", status_code=303)


@router.post("/usuarios/{uid}/pausar_form")
async def pausar_form(
    uid: int, admin: dict = Depends(get_admin_from_cookie), dias: int = Form(7)
):
    await admin_api.pausar_usuario(uid=uid, req=admin_api.PausarReq(dias=dias), admin=admin)
    return RedirectResponse(url=f"/admin/usuarios/{uid}", status_code=303)


@router.post("/usuarios/{uid}/bloquear_form")
async def bloquear_form(
    uid: int,
    admin: dict = Depends(get_admin_from_cookie),
    motivo: str = Form(...),
):
    await admin_api.bloquear_endpoint(uid=uid, req=admin_api.BloquearReq(motivo=motivo), admin=admin)
    return RedirectResponse(url=f"/admin/usuarios/{uid}", status_code=303)


@router.post("/usuarios/{uid}/desbloquear_form")
async def desbloquear_form(
    uid: int, admin: dict = Depends(get_admin_from_cookie)
):
    await admin_api.desbloquear_endpoint(uid=uid, admin=admin)
    return RedirectResponse(url=f"/admin/usuarios/{uid}", status_code=303)


@router.post("/usuarios/{uid}/eliminar_form")
async def eliminar_form(
    uid: int, admin: dict = Depends(get_admin_from_cookie)
):
    await require_super(admin)
    await admin_api.eliminar_endpoint(uid=uid, admin=admin)
    return RedirectResponse(url="/admin/usuarios", status_code=303)


# -----------------------------------------------------------------------------
# Pagos
# -----------------------------------------------------------------------------


@router.get("/pagos", response_class=HTMLResponse)
async def pagos_lista(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    estado: Optional[str] = "pendiente_humano",
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    data = await admin_api.listar_pagos(
        admin=admin, estado=estado, limit=limit, offset=offset
    )
    template = "admin/_pagos_tabla.html" if request.headers.get("hx-request") else "admin/pagos.html"
    return render(
        request,
        template,
        {
            "admin": admin,
            "data": data,
            "filtros": {"estado": estado, "limit": limit, "offset": offset},
            "active": "pagos",
        },
    )


@router.get("/pagos/{comp_id}/foto")
async def pago_foto_cookie(
    comp_id: int, admin: dict = Depends(get_admin_from_cookie)
):
    """Proxy foto del comprobante via Telegram API. Autenticado por cookie.

    El router JSON (/admin/pagos/{id}/foto en admin.py) usa header Bearer
    que no funciona desde <img src="..."> en el browser. Esta ruta duplica
    la logica pero acepta la cookie HttpOnly del panel HTML.
    """
    from fastapi.responses import Response

    import httpx

    from src.config import settings as _settings
    from src.db.repository import obtener_comprobante

    comp = await obtener_comprobante(comp_id)
    if comp is None or not comp.foto_file_id:
        raise HTTPException(404, "Comprobante o foto no encontrada")

    token = _settings.telegram_token.get_secret_value()
    async with httpx.AsyncClient(timeout=10.0) as client:
        info = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": comp.foto_file_id},
        )
        info.raise_for_status()
        data = info.json()
        if not data.get("ok"):
            raise HTTPException(502, "getFile fallo")
        file_path = data["result"]["file_path"]
        download = await client.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}"
        )
        download.raise_for_status()
    return Response(content=download.content, media_type="image/jpeg")


@router.get("/pagos/{comp_id}", response_class=HTMLResponse)
async def pago_detalle(
    comp_id: int, request: Request, admin: dict = Depends(get_admin_from_cookie)
):
    data = await admin_api.detalle_pago(comp_id=comp_id, admin=admin)
    return render(
        request,
        "admin/pago_detalle.html",
        {"admin": admin, "data": data, "comp_id": comp_id, "active": "pagos"},
    )


@router.post("/pagos/{comp_id}/aprobar_form")
async def pago_aprobar_form(
    comp_id: int,
    admin: dict = Depends(get_admin_from_cookie),
    notas: str = Form(""),
):
    await admin_api.aprobar(comp_id=comp_id, req=admin_api.AprobarReq(notas=notas), admin=admin)
    return RedirectResponse(
        url=f"/admin/pagos?msg=Pago+%23{comp_id}+aprobado.+Plan+activado.", status_code=303
    )


@router.post("/pagos/{comp_id}/rechazar_form")
async def pago_rechazar_form(
    comp_id: int,
    admin: dict = Depends(get_admin_from_cookie),
    motivo: str = Form(...),
    bloquear: bool = Form(False),
):
    await admin_api.rechazar(
        comp_id=comp_id, req=admin_api.RechazarReq(motivo=motivo, bloquear=bloquear), admin=admin
    )
    return RedirectResponse(
        url=f"/admin/pagos?msg=Pago+%23{comp_id}+rechazado.", status_code=303
    )


# -----------------------------------------------------------------------------
# Crisis
# -----------------------------------------------------------------------------


@router.get("/crisis", response_class=HTMLResponse)
async def crisis_lista(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    nivel: Optional[int] = None,
    dias: int = 30,
    limit: int = Query(100, le=500),
):
    data = await admin_api.listar_crisis(admin=admin, nivel=nivel, dias=dias, limit=limit)
    return render(
        request,
        "admin/crisis.html",
        {
            "admin": admin,
            "data": data,
            "filtros": {"nivel": nivel, "dias": dias, "limit": limit},
            "active": "crisis",
        },
    )


# -----------------------------------------------------------------------------
# Finanzas
# -----------------------------------------------------------------------------


@router.get("/finanzas", response_class=HTMLResponse)
async def finanzas_view(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    dias: int = 30,
):
    data = await admin_api.finanzas(admin=admin, dias=dias)
    return render(
        request,
        "admin/finanzas.html",
        {"admin": admin, "data": data, "dias": dias, "active": "finanzas"},
    )


# -----------------------------------------------------------------------------
# Operaciones (broadcast)
# -----------------------------------------------------------------------------


@router.get("/operaciones", response_class=HTMLResponse)
async def operaciones_view(
    request: Request, admin: dict = Depends(get_admin_from_cookie)
):
    await require_super(admin)
    return render(
        request,
        "admin/operaciones.html",
        {"admin": admin, "active": "operaciones", "result": None},
    )


@router.post("/operaciones/broadcast_form", response_class=HTMLResponse)
async def broadcast_form(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    mensaje: str = Form(...),
    plan_minimo: Optional[str] = Form(None),
    pais: Optional[str] = Form(None),
    silent: bool = Form(True),
    gm_nombre: Optional[str] = Form(None),
):
    await require_super(admin)
    result = await admin_api.broadcast(
        req=admin_api.BroadcastReq(
            mensaje=mensaje,
            plan_minimo=plan_minimo or None,
            pais=pais or None,
            silent=silent,
            gm_nombre=gm_nombre or None,
        ),
        admin=admin,
    )
    return render(
        request,
        "admin/operaciones.html",
        {"admin": admin, "active": "operaciones", "result": result},
    )


# -----------------------------------------------------------------------------
# Desafíos diarios
# -----------------------------------------------------------------------------


@router.get("/desafios", response_class=HTMLResponse)
async def desafios_view(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    fecha: Optional[str] = Query(None),
):
    await require_super(admin)
    data = await admin_api.admin_desafios(fecha=fecha, _admin=admin)
    return render(
        request,
        "admin/desafios.html",
        {
            "admin": admin,
            "active": "desafios",
            "data": data,
            "fecha": data["fecha"],
        },
    )


@router.post("/desafios/generar_form")
async def desafios_generar_form(
    admin: dict = Depends(get_admin_from_cookie),
    fecha: Optional[str] = Form(None),
):
    await require_super(admin)
    result = await admin_api.admin_desafios_generar(
        req=admin_api.DesafioGenerarReq(fecha=fecha or None),
        admin=admin,
    )
    n = result.get("generados", 0)
    return RedirectResponse(
        url=f"/admin/desafios?fecha={result['fecha']}&msg=Generados+{n}+desafios.",
        status_code=303,
    )


@router.post("/desafios/{desafio_id}/cerrar_form")
async def desafios_cerrar_form(
    desafio_id: int,
    admin: dict = Depends(get_admin_from_cookie),
    fecha: Optional[str] = Form(None),
):
    await require_super(admin)
    await admin_api.admin_desafios_cerrar(desafio_id=desafio_id, admin=admin)
    q = f"fecha={fecha}" if fecha else ""
    sep = "&" if q else ""
    return RedirectResponse(
        url=f"/admin/desafios?{q}{sep}msg=Desafio+%23{desafio_id}+en+cierre.",
        status_code=303,
    )


# -----------------------------------------------------------------------------
# Admins
# -----------------------------------------------------------------------------


@router.get("/admins", response_class=HTMLResponse)
async def admins_lista(
    request: Request, admin: dict = Depends(get_admin_from_cookie)
):
    await require_super(admin)
    items = await admin_api.listar_admins(admin=admin)
    return render(
        request,
        "admin/admins.html",
        {"admin": admin, "items": items, "active": "admins", "error": None, "ok": None},
    )


@router.post("/admins/crear_form", response_class=HTMLResponse)
async def admin_crear_form(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    email: str = Form(...),
    password: str = Form(...),
    rol: str = Form("soporte"),
):
    await require_super(admin)
    error = None
    ok = None
    try:
        nuevo = await admin_api.crear_admin(
            req=admin_api.CrearAdminReq(email=email, password=password, rol=rol),
            admin=admin,
        )
        ok = f"Admin creado: {nuevo['email']} ({nuevo['rol']})"
    except HTTPException as exc:
        error = exc.detail
    items = await admin_api.listar_admins(admin=admin)
    return render(
        request,
        "admin/admins.html",
        {"admin": admin, "items": items, "active": "admins", "error": error, "ok": ok},
    )


# ============================================================================
# Costos API
# ============================================================================


@router.get("/costos", response_class=HTMLResponse)
async def costos_dashboard(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    dias: int = Query(30),
    servicio: str = Query(""),
):
    from src.db.connection import async_session_factory
    from src.db.models import LlmUsage, Usuario

    desde = datetime.utcnow() - timedelta(days=dias)
    async with async_session_factory() as session:
        base_filter = [LlmUsage.creado_en >= desde]
        if servicio:
            base_filter.append(LlmUsage.servicio == servicio)

        tot = await session.execute(
            select(
                func.count(LlmUsage.id),
                func.coalesce(func.sum(LlmUsage.input_tokens), 0),
                func.coalesce(func.sum(LlmUsage.output_tokens), 0),
                func.coalesce(func.sum(LlmUsage.costo_estimado_usd), 0.0),
            ).where(*base_filter)
        )
        row = tot.one()
        totales = {"llamadas": row[0], "input": row[1], "output": row[2], "costo": row[3]}

        srv_q = await session.execute(
            select(
                LlmUsage.servicio,
                func.count(LlmUsage.id),
                func.sum(LlmUsage.input_tokens),
                func.sum(LlmUsage.output_tokens),
                func.sum(LlmUsage.costo_estimado_usd),
            ).where(*base_filter).group_by(LlmUsage.servicio).order_by(func.sum(LlmUsage.costo_estimado_usd).desc())
        )
        por_servicio = [
            {"servicio": r[0], "llamadas": r[1], "input": r[2] or 0, "output": r[3] or 0, "costo": r[4] or 0}
            for r in srv_q
        ]

        mod_q = await session.execute(
            select(
                LlmUsage.modelo,
                func.count(LlmUsage.id),
                func.sum(LlmUsage.input_tokens),
                func.sum(LlmUsage.output_tokens),
                func.sum(LlmUsage.costo_estimado_usd),
            ).where(*base_filter).group_by(LlmUsage.modelo).order_by(func.sum(LlmUsage.costo_estimado_usd).desc())
        )
        por_modelo = [
            {"modelo": r[0], "llamadas": r[1], "input": r[2] or 0, "output": r[3] or 0, "costo": r[4] or 0}
            for r in mod_q
        ]

        top_q = await session.execute(
            select(
                LlmUsage.telegram_id,
                func.count(LlmUsage.id),
                func.sum(LlmUsage.input_tokens),
                func.sum(LlmUsage.output_tokens),
                func.sum(LlmUsage.costo_estimado_usd),
            ).where(*base_filter, LlmUsage.telegram_id.isnot(None))
            .group_by(LlmUsage.telegram_id)
            .order_by(func.sum(LlmUsage.costo_estimado_usd).desc())
            .limit(10)
        )
        top_rows = top_q.all()
        tg_ids = [r[0] for r in top_rows]
        nombres = {}
        if tg_ids:
            n_q = await session.execute(
                select(Usuario.telegram_id, Usuario.nombre).where(Usuario.telegram_id.in_(tg_ids))
            )
            nombres = {r[0]: r[1] for r in n_q}
        top_usuarios = [
            {"telegram_id": r[0], "nombre": nombres.get(r[0], ""), "llamadas": r[1], "input": r[2] or 0, "output": r[3] or 0, "costo": r[4] or 0}
            for r in top_rows
        ]

        fecha_col = cast(LlmUsage.creado_en, Date)
        dia_q = await session.execute(
            select(
                fecha_col.label("dia"),
                func.sum(LlmUsage.costo_estimado_usd),
            ).where(*base_filter)
            .group_by(fecha_col)
            .order_by(fecha_col)
        )
        serie_diaria = [{"fecha": str(r[0]), "costo": r[1] or 0} for r in dia_q]

        srv_list_q = await session.execute(
            select(LlmUsage.servicio).distinct()
        )
        servicios_disponibles = sorted([r[0] for r in srv_list_q])

    return render(
        request,
        "admin/costos.html",
        {
            "admin": admin,
            "active": "costos",
            "dias": dias,
            "servicio_filtro": servicio,
            "servicios_disponibles": servicios_disponibles,
            "totales": totales,
            "por_servicio": por_servicio,
            "por_modelo": por_modelo,
            "top_usuarios": top_usuarios,
            "serie_diaria": serie_diaria,
        },
    )


@router.get("/costos/csv")
async def costos_csv(
    admin: dict = Depends(get_admin_from_cookie),
    dias: int = Query(30),
    servicio: str = Query(""),
):
    from src.db.connection import async_session_factory
    from src.db.models import LlmUsage, Usuario

    desde = datetime.utcnow() - timedelta(days=dias)
    async with async_session_factory() as session:
        q = select(
            LlmUsage.creado_en,
            LlmUsage.telegram_id,
            Usuario.nombre,
            LlmUsage.servicio,
            LlmUsage.modelo,
            LlmUsage.input_tokens,
            LlmUsage.output_tokens,
            LlmUsage.costo_estimado_usd,
            LlmUsage.rounds,
        ).outerjoin(Usuario, Usuario.id == LlmUsage.usuario_id).where(
            LlmUsage.creado_en >= desde
        ).order_by(LlmUsage.creado_en.desc())
        if servicio:
            q = q.where(LlmUsage.servicio == servicio)
        rows = (await session.execute(q)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["fecha", "telegram_id", "usuario", "servicio", "modelo", "input_tokens", "output_tokens", "costo_usd", "rounds"])
    for r in rows:
        writer.writerow([
            r[0].strftime("%Y-%m-%d %H:%M:%S") if r[0] else "",
            r[1] or "",
            r[2] or "",
            r[3],
            r[4],
            r[5],
            r[6],
            f"{r[7]:.6f}",
            r[8],
        ])
    buf.seek(0)
    filename = f"costos_api_{date.today().isoformat()}.csv"
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -----------------------------------------------------------------------------
# Auditoría de Turnos y Conversaciones
# -----------------------------------------------------------------------------


@router.get("/auditoria", response_class=HTMLResponse)
async def auditoria_lista(
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
    telegram_id: Optional[int] = Query(None),
    request_id: Optional[str] = Query(None),
    con_error: Optional[bool] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    data = await admin_api.listar_auditoria(
        admin=admin,
        telegram_id=telegram_id,
        request_id=request_id,
        con_error=con_error,
        limit=limit,
        offset=offset,
    )
    template = "admin/_auditoria_tabla.html" if request.headers.get("hx-request") else "admin/auditoria.html"
    return render(
        request,
        template,
        {
            "admin": admin,
            "data": data,
            "filtros": {
                "telegram_id": telegram_id or "",
                "request_id": request_id or "",
                "con_error": con_error,
                "limit": limit,
                "offset": offset,
            },
            "active": "auditoria",
        },
    )


@router.get("/auditoria/{request_id}", response_class=HTMLResponse)
async def auditoria_detalle(
    request_id: str,
    request: Request,
    admin: dict = Depends(get_admin_from_cookie),
):
    data = await admin_api.detalle_auditoria(request_id=request_id, admin=admin)
    return render(
        request,
        "admin/auditoria_detalle.html",
        {
            "admin": admin,
            "row": data,
            "active": "auditoria",
        },
    )
