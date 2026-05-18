"""OAuth callbacks para wearables (Whoop, Garmin, Strava, Google Fit).

Despues del OAuth dance, guarda tokens cifrados y dispara primer sync.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.config import settings
from src.services.wearables import (
    PROVEEDORES_DISPONIBLES,
    upsert_integracion,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integraciones", tags=["integraciones"])


TOKEN_URLS = {
    "whoop": "https://api.prod.whoop.com/oauth/oauth2/token",
    "strava": "https://www.strava.com/oauth/token",
    "google_fit": "https://oauth2.googleapis.com/token",
    "garmin": "https://connectapi.garmin.com/oauth-service/oauth/access_token",
}


def _telegram_id_from_state(state: str) -> Optional[int]:
    if "." not in state:
        return None
    try:
        return int(state.rsplit(".", 1)[1])
    except ValueError:
        return None


def _client_credentials(proveedor: str) -> tuple[str, str, str]:
    cid = os.environ.get(f"{proveedor.upper()}_CLIENT_ID", "")
    csec = os.environ.get(f"{proveedor.upper()}_CLIENT_SECRET", "")
    # El callback OAuth lo recibe la API del bot (este router se monta en
    # src/main.py bajo /api/integraciones/*), no el admin web. Por eso
    # webhook_base_url y NO admin_url. Fallback al dominio Railway real.
    api_base = str(
        settings.webhook_base_url
        or "https://entrenadorpersonal-production.up.railway.app"
    ).rstrip("/")
    redirect = f"{api_base}/api/integraciones/{proveedor}/callback"
    return cid, csec, redirect


async def _intercambiar_codigo_por_token(
    proveedor: str, code: str
) -> Optional[dict]:
    token_url = TOKEN_URLS.get(proveedor)
    if not token_url:
        return None
    cid, csec, redirect = _client_credentials(proveedor)
    if not cid or not csec:
        logger.error("Faltan credenciales OAuth para %s", proveedor)
        return None
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect,
        "client_id": cid,
        "client_secret": csec,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(token_url, data=payload)
            r.raise_for_status()
            return r.json()
    except Exception:
        logger.exception("Error intercambiando code por token %s", proveedor)
        return None


@router.get("/{proveedor}/callback", response_class=HTMLResponse)
async def oauth_callback(
    proveedor: str,
    code: str = Query(""),
    state: str = Query(""),
    error: str = Query(""),
):
    if proveedor not in PROVEEDORES_DISPONIBLES:
        raise HTTPException(404, "proveedor invalido")
    if error:
        return HTMLResponse(
            f"<h2>Error: {error}</h2><p>Cierra esta ventana y reintenta.</p>",
            status_code=400,
        )
    if not code:
        raise HTTPException(400, "code requerido")
    telegram_id = _telegram_id_from_state(state)
    if telegram_id is None:
        raise HTTPException(400, "state invalido")

    tokens = await _intercambiar_codigo_por_token(proveedor, code)
    if tokens is None:
        return HTMLResponse(
            "<h2>No pude intercambiar el codigo.</h2><p>Cierra y reintenta.</p>",
            status_code=502,
        )

    access_token = tokens.get("access_token", "")
    refresh_token = tokens.get("refresh_token", "")
    expires_in = int(tokens.get("expires_in", 3600))
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    external_user_id = str(
        tokens.get("user_id") or tokens.get("athlete", {}).get("id", "") or ""
    )

    integ = await upsert_integracion(
        telegram_id=telegram_id,
        proveedor=proveedor,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        external_user_id=external_user_id,
    )
    if integ is None:
        return HTMLResponse(
            "<h2>Usuario no encontrado.</h2>", status_code=404
        )

    return HTMLResponse(
        f"<!doctype html><html><head><title>Conectado</title>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'></head>"
        f"<body style='font-family: system-ui; max-width: 480px; margin: 40px auto; padding: 24px;'>"
        f"<h1>{proveedor.title()} conectado</h1>"
        f"<p>Tus datos se sincronizaran en los proximos minutos.</p>"
        f"<p>Cierra esta pestana y vuelve a Telegram.</p>"
        f"</body></html>"
    )
