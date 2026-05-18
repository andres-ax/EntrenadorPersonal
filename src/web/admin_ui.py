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

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

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
    return RedirectResponse(url="/admin/pagos", status_code=303)


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
    return RedirectResponse(url="/admin/pagos", status_code=303)


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
):
    await require_super(admin)
    result = await admin_api.broadcast(
        req=admin_api.BroadcastReq(
            mensaje=mensaje,
            plan_minimo=plan_minimo or None,
            pais=pais or None,
            silent=silent,
        ),
        admin=admin,
    )
    return render(
        request,
        "admin/operaciones.html",
        {"admin": admin, "active": "operaciones", "result": result},
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
