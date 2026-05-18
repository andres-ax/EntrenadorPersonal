"""Singleton de Jinja2Templates compartido por landing/admin/miniapp.

Configura:
- Directorio de templates: `<repo>/frontend/templates/`
- Filtros custom: `cop` (formato peso colombiano), `humano` (fechas relativas)
- Globals: `settings`, helpers de URL
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from src.config import settings

TEMPLATES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "templates"
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _fmt_cop(value: int | float | None) -> str:
    """Formatea pesos colombianos: 5000 -> $5.000."""
    if value is None:
        return "-"
    try:
        n = int(value)
    except (TypeError, ValueError):
        return str(value)
    return "$" + f"{n:,}".replace(",", ".")


def _fmt_humano(value: str | datetime | None) -> str:
    """Convierte ISO o datetime a 'hace 3 horas'."""
    if not value:
        return "-"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - value
    secs = int(delta.total_seconds())
    if secs < 60:
        return "hace un momento"
    if secs < 3600:
        return f"hace {secs // 60} min"
    if secs < 86400:
        return f"hace {secs // 3600} h"
    if secs < 86400 * 7:
        return f"hace {secs // 86400} d"
    return value.strftime("%Y-%m-%d")


def _fmt_fecha(value: str | datetime | None) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value.strftime("%Y-%m-%d %H:%M")


templates.env.filters["cop"] = _fmt_cop
templates.env.filters["humano"] = _fmt_humano
templates.env.filters["fecha"] = _fmt_fecha

# Globals expuestos a TODAS las plantillas
templates.env.globals["settings"] = settings
templates.env.globals["ahora_year"] = datetime.now().year


def render(request: Request, name: str, ctx: dict | None = None):
    """Atajo: renderiza `name` con el `request` incluido automaticamente.

    Importante: la API nueva de Starlette (>=0.30) requiere `request` como
    primer argumento posicional. Si lo invocas como (name, context) la
    libreria interpreta `name=context` y termina pasando un dict como key
    del cache Jinja2 (TypeError: unhashable type: 'dict').
    """
    return templates.TemplateResponse(request, name, ctx or {})
