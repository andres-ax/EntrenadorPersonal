"""Landing publica (server-side Jinja2).

Reemplaza el antiguo `frontend/landing/` Astro. Sirve `/`, `/precios`,
`/deportes`, `/deportes/{slug}`, `/politicas/*`, `/sitemap.xml`, `/robots.txt`.

Importante: este router se incluye DESPUES de los routers de admin y app
para que rutas dinamicas como `/admin/*` o `/app/*` ganen sobre el
catch-all de la landing.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import (HTMLResponse, PlainTextResponse,
                               RedirectResponse, Response)

from src.api.admin_auth import (ADMIN_COOKIE_NAME, ADMIN_JWT_TTL, LoginRequest,
                                autenticar_admin)
from src.api.auth import JWT_TTL_SECONDS, _sign_jwt
from src.config import settings
from src.data.deportes import DEPORTES, deporte_por_slug
from src.services.codigo_web import validar_y_consumir
from src.telegram.middlewares import check_rate_limit_ip
from src.web.templates import render

router = APIRouter(tags=["landing"], include_in_schema=False)


def _canonical(request: Request, path: str = "") -> str:
    """Construye URL canonical absoluta para SEO."""
    base = str(settings.landing_url or request.base_url).rstrip("/")
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return render(
        request,
        "landing/index.html",
        {"canonical": _canonical(request, "/"), "active": "home"},
    )


@router.get("/precios", response_class=HTMLResponse)
async def precios(request: Request):
    return render(
        request,
        "landing/precios.html",
        {
            "canonical": _canonical(request, "/precios"),
            "active": "precios",
            "precios": {
                "starter": settings.precio_starter_cop,
                "pro": settings.precio_pro_cop,
                "elite": settings.precio_elite_cop,
                "lifetime": settings.precio_lifetime_cop,
                "descuento_anual_pct": settings.descuento_anual_pct,
                "cupos_lifetime": settings.cupos_lifetime_total,
            },
        },
    )


@router.get("/deportes", response_class=HTMLResponse)
async def deportes_index(request: Request):
    return render(
        request,
        "landing/deportes_index.html",
        {
            "canonical": _canonical(request, "/deportes"),
            "active": "deportes",
            "deportes": DEPORTES,
        },
    )


@router.get("/deportes/{slug}", response_class=HTMLResponse)
async def deporte_detalle(slug: str, request: Request):
    deporte = deporte_por_slug(slug)
    if deporte is None:
        raise HTTPException(status_code=404, detail="Deporte no encontrado")
    return render(
        request,
        "landing/deporte_detalle.html",
        {
            "canonical": _canonical(request, f"/deportes/{slug}"),
            "active": "deportes",
            "deporte": deporte,
        },
    )


@router.get("/politicas/privacidad", response_class=HTMLResponse)
async def politicas_privacidad(request: Request):
    return render(
        request,
        "landing/politicas/privacidad.html",
        {"canonical": _canonical(request, "/politicas/privacidad")},
    )


@router.get("/politicas/terminos", response_class=HTMLResponse)
async def politicas_terminos(request: Request):
    return render(
        request,
        "landing/politicas/terminos.html",
        {"canonical": _canonical(request, "/politicas/terminos")},
    )


@router.get("/politicas/manejo-datos-tca", response_class=HTMLResponse)
async def politicas_tca(request: Request):
    return render(
        request,
        "landing/politicas/manejo-datos-tca.html",
        {"canonical": _canonical(request, "/politicas/manejo-datos-tca")},
    )


# =============================================================================
# Login unificado de la landing (deportistas + admins)
# =============================================================================


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    tab: str = "deportista",
    error: str | None = None,
):
    """Pagina de login con dos tabs: Deportista (codigo Telegram) y Admin."""
    return render(
        request,
        "landing/login.html",
        {
            "canonical": _canonical(request, "/login"),
            "active_tab": tab if tab in ("deportista", "admin") else "deportista",
            "error": error,
        },
    )


@router.post("/login/deportista", response_class=HTMLResponse)
async def login_deportista_submit(request: Request, codigo: str = Form(...)):
    """Valida el codigo de 6 digitos generado por /codigo_web en el bot."""
    ip = request.client.host if request.client else "unknown"
    if not await check_rate_limit_ip(ip, max_per_minute=5):
        raise HTTPException(429, "Demasiados intentos. Espera un momento.")
    uid = await validar_y_consumir(codigo.strip())
    if uid is None:
        return render(
            request,
            "landing/login.html",
            {
                "canonical": _canonical(request, "/login"),
                "active_tab": "deportista",
                "error": "Codigo invalido o expirado. Pide uno nuevo con /codigo_web en el bot.",
            },
        )
    response = RedirectResponse(url="/app/dashboard", status_code=303)
    response.set_cookie(
        key="user_jwt",
        value=_sign_jwt(uid),
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return response


@router.post("/login/admin", response_class=HTMLResponse)
async def login_admin_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    """Login admin via email + password (mismo backend que /admin/login)."""
    ip = request.client.host if request.client else "unknown"
    if not await check_rate_limit_ip(ip, max_per_minute=5):
        raise HTTPException(429, "Demasiados intentos. Espera un momento.")
    try:
        resp_login = await autenticar_admin(
            LoginRequest(email=email, password=password)
        )
    except HTTPException as exc:
        return render(
            request,
            "landing/login.html",
            {
                "canonical": _canonical(request, "/login"),
                "active_tab": "admin",
                "error": exc.detail,
                "email_prefill": email,
            },
        )
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
    return response


@router.get("/logout")
async def logout_unificado():
    """Borra ambas cookies de sesion (deportista y admin) y vuelve al home."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("user_jwt", path="/")
    response.delete_cookie(ADMIN_COOKIE_NAME, path="/")
    return response


@router.get("/sitemap.xml")
async def sitemap(request: Request):
    """Sitemap XML dinamico: paginas estaticas + 1 entrada por deporte."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls: list[tuple[str, str, float]] = [
        ("/", "weekly", 1.0),
        ("/precios", "weekly", 0.9),
        ("/deportes", "weekly", 0.8),
        ("/politicas/privacidad", "monthly", 0.3),
        ("/politicas/terminos", "monthly", 0.3),
        ("/politicas/manejo-datos-tca", "monthly", 0.3),
    ]
    for d in DEPORTES:
        urls.append((f"/deportes/{d['slug']}", "monthly", 0.6))

    parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for path, freq, prio in urls:
        parts.append("<url>")
        parts.append(f"<loc>{_canonical(request, path)}</loc>")
        parts.append(f"<lastmod>{now}</lastmod>")
        parts.append(f"<changefreq>{freq}</changefreq>")
        parts.append(f"<priority>{prio:.1f}</priority>")
        parts.append("</url>")
    parts.append("</urlset>")
    return Response(content="\n".join(parts), media_type="application/xml")


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots(request: Request):
    return (
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /app/\n"
        "Allow: /\n"
        f"\nSitemap: {_canonical(request, '/sitemap.xml')}\n"
    )
