"""Mini app de Telegram (server-side Jinja2 + HTMX + vanilla JS).

Reemplaza el antiguo `frontend/miniapp/` Vite/React. Sirve `/app/*`.

Auth: cookie HttpOnly `user_jwt` puesta por `POST /api/auth/initdata` cuando
el cliente envia el initData de Telegram. Si la cookie no existe, redirige
a una pagina que pide abrir desde Telegram (no se puede generar initData
desde un browser comun).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.auth import verify_jwt
from src.web.templates import render

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/app", tags=["miniapp"], include_in_schema=False)


USER_COOKIE_NAME = "user_jwt"


async def get_user_from_cookie(
    request: Request, user_jwt: str | None = Cookie(default=None, alias=USER_COOKIE_NAME)
) -> dict | None:
    """Devuelve dict {uid: int} si la cookie es valida, sino None.

    NO levanta excepcion: las paginas del mini app deciden que hacer
    cuando no hay sesion (mostrar mensaje "abrime desde Telegram").
    """
    if not user_jwt:
        return None
    uid = verify_jwt(user_jwt)
    if uid is None:
        return None
    return {"uid": uid}


@router.get("/", response_class=HTMLResponse)
async def app_root(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return render(request, "app/sin_sesion.html", {})
    return RedirectResponse(url="/app/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return render(request, "app/sin_sesion.html", {})
    return render(request, "app/dashboard.html", {"user": user, "active": "dashboard"})


@router.get("/calendario", response_class=HTMLResponse)
async def calendario(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return render(request, "app/sin_sesion.html", {})
    return render(request, "app/calendario.html", {"user": user, "active": "calendario"})


@router.get("/plan", response_class=HTMLResponse)
async def plan(request: Request, user: dict | None = Depends(get_user_from_cookie)):
    if user is None:
        return render(request, "app/sin_sesion.html", {})
    return render(request, "app/plan.html", {"user": user, "active": "plan"})


@router.get("/prs", response_class=HTMLResponse)
async def prs(request: Request, user: dict | None = Depends(get_user_from_cookie)):
    if user is None:
        return render(request, "app/sin_sesion.html", {})
    return render(request, "app/prs.html", {"user": user, "active": "prs"})


@router.get("/settings", response_class=HTMLResponse)
async def settings_view(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return render(request, "app/sin_sesion.html", {})
    return render(request, "app/settings.html", {"user": user, "active": "settings"})


@router.get("/pagar", response_class=HTMLResponse)
async def pagar(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    from src.config import settings

    return render(
        request,
        "app/pagar.html",
        {
            "user": user,
            "active": "pagar",
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
        return render(request, "app/sin_sesion.html", {})
    return render(request, "app/llamar.html", {"user": user, "active": "llamar"})


@router.get("/wearables", response_class=HTMLResponse)
async def wearables(
    request: Request, user: dict | None = Depends(get_user_from_cookie)
):
    if user is None:
        return render(request, "app/sin_sesion.html", {})
    return render(request, "app/wearables.html", {"user": user, "active": "wearables"})
