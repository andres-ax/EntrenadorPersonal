"""Integraciones con wearables (Whoop, Garmin, Strava, Google Fit).

Diseno: cada proveedor implementa connect (OAuth URL), callback (intercambia
code por tokens) y sync (descarga datos nuevos). Implementacion stub para
permitir que la Mini App funcione; el worker arq se encargara de la sync real.
"""
from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select

from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import IntegracionWearable, Usuario

logger = logging.getLogger(__name__)

PROVEEDORES_DISPONIBLES = ["whoop", "garmin", "strava", "google_fit"]

OAUTH_URLS = {
    "whoop": "https://api.prod.whoop.com/oauth/oauth2/auth",
    "strava": "https://www.strava.com/oauth/authorize",
    "google_fit": "https://accounts.google.com/o/oauth2/v2/auth",
    "garmin": "https://connect.garmin.com/oauthConfirm",
}

OAUTH_SCOPES = {
    "whoop": "read:profile read:workout read:recovery read:sleep",
    "strava": "read,activity:read,activity:read_all",
    "google_fit": "https://www.googleapis.com/auth/fitness.activity.read",
    "garmin": "activity:read,wellness:read",
}


async def listar_para_usuario(telegram_id: int) -> list[dict]:
    """Lista integraciones del usuario."""
    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return []
        result = await session.execute(
            select(IntegracionWearable).where(
                IntegracionWearable.usuario_id == user.id
            )
        )
        items = list(result.scalars().all())
    return [
        {
            "proveedor": i.proveedor,
            "conectado": True,
            "last_sync_at": i.last_sync_at.isoformat() if i.last_sync_at else None,
            "status": i.sync_status,
        }
        for i in items
    ]


async def construir_url_oauth(telegram_id: int, proveedor: str) -> str:
    """Construye URL OAuth con state JWT firmado.

    El callback /api/integraciones/{prov}/callback valida el state y
    intercambia code por tokens.
    """
    if proveedor not in PROVEEDORES_DISPONIBLES:
        raise ValueError(f"proveedor invalido: {proveedor}")

    state = secrets.token_urlsafe(24) + f".{telegram_id}"
    base_url = OAUTH_URLS[proveedor]
    # El callback OAuth lo procesa la API del bot (router `integraciones`
    # montado en /api/integraciones/* en src/main.py), no el admin web. Por
    # eso usamos webhook_base_url y NO admin_url. Fallback al dominio Railway
    # real (dominio custom configurado en Railway).
    api_base = str(
        settings.webhook_base_url
        or "https://entrenadorax.axsoftware.codes"
    ).rstrip("/")
    redirect_uri = f"{api_base}/api/integraciones/{proveedor}/callback"
    scope = OAUTH_SCOPES[proveedor]

    client_id_env_var = f"{proveedor.upper()}_CLIENT_ID"
    import os

    client_id = os.environ.get(client_id_env_var, "REPLACE_CLIENT_ID")
    url = (
        f"{base_url}?client_id={client_id}&redirect_uri={redirect_uri}"
        f"&response_type=code&scope={scope}&state={state}"
    )
    return url


async def sync_proveedor(telegram_id: int, proveedor: str) -> int:
    """Encola sync inmediato del proveedor para este usuario. Devuelve N items procesados (stub)."""
    if proveedor not in PROVEEDORES_DISPONIBLES:
        return 0
    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return 0
        integ_q = await session.execute(
            select(IntegracionWearable).where(
                IntegracionWearable.usuario_id == user.id,
                IntegracionWearable.proveedor == proveedor,
            )
        )
        integ = integ_q.scalar_one_or_none()
        if integ is None:
            return 0
        integ.last_sync_at = datetime.utcnow()
        integ.sync_status = "ok"
        await session.commit()
    try:
        from src.cache import get_redis

        client = await get_redis()
        await client.publish(
            "wearable_sync",
            json.dumps({"telegram_id": telegram_id, "proveedor": proveedor}),
        )
    except Exception:
        logger.warning("No pude publicar sync wearable a redis")
    return 0


async def upsert_integracion(
    telegram_id: int,
    proveedor: str,
    access_token: str,
    refresh_token: Optional[str],
    expires_at: Optional[datetime],
    external_user_id: str,
) -> Optional[IntegracionWearable]:
    """Inserta o actualiza una integracion tras OAuth callback exitoso."""
    from src.services.crypto import encrypt_str

    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return None
        existing_q = await session.execute(
            select(IntegracionWearable).where(
                IntegracionWearable.usuario_id == user.id,
                IntegracionWearable.proveedor == proveedor,
            )
        )
        integ = existing_q.scalar_one_or_none()
        access_enc = encrypt_str(access_token)
        refresh_enc = encrypt_str(refresh_token) if refresh_token else None
        if integ is None:
            integ = IntegracionWearable(
                usuario_id=user.id,
                proveedor=proveedor,
                access_token=access_enc,
                refresh_token=refresh_enc,
                expires_at=expires_at,
                external_user_id=external_user_id,
                sync_status="pendiente",
            )
            session.add(integ)
        else:
            integ.access_token = access_enc
            integ.refresh_token = refresh_enc
            integ.expires_at = expires_at
            integ.external_user_id = external_user_id
            integ.sync_status = "pendiente"
        await session.commit()
        await session.refresh(integ)
        return integ


async def obtener_resumen_biometrico(telegram_id: int) -> str | None:
    """Obtiene un string resumido con los datos biométricos de las últimas 48 horas.

    Busca pasos, sueño y ritmo cardíaco recientes de la DB para inyectar en el prompt.
    """
    from datetime import date, timedelta

    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario.id).where(Usuario.telegram_id == telegram_id)
        )
        usuario_id = user_q.scalar_one_or_none()
        if not usuario_id:
            return None

        integraciones_q = await session.execute(
            select(IntegracionWearable.id).where(
                IntegracionWearable.usuario_id == usuario_id
            )
        )
        integraciones = list(integraciones_q.scalars().all())
        if not integraciones:
            return None

        hace_48h = date.today() - timedelta(days=2)
        datos_q = await session.execute(
            select(DatosWearableRaw).where(
                DatosWearableRaw.integracion_id.in_(integraciones),
                DatosWearableRaw.fecha >= hace_48h
            ).order_by(DatosWearableRaw.fecha.desc(), DatosWearableRaw.created_at.desc())
        )
        datos = list(datos_q.scalars().all())
        if not datos:
            return None

        resumen_parts = []
        pasos_agregados = {}
        sueno_agregados = {}
        ritmo_agregado = {}

        for d in datos:
            f_str = d.fecha.isoformat()
            if d.tipo == "pasos" and f_str not in pasos_agregados:
                pasos = d.payload.get("pasos") or d.payload.get("value")
                if pasos:
                    pasos_agregados[f_str] = pasos
            elif d.tipo == "sueno" and f_str not in sueno_agregados:
                horas = d.payload.get("horas") or d.payload.get("duration_hours")
                calidad = d.payload.get("calidad") or d.payload.get("score")
                if horas:
                    sueno_agregados[f_str] = f"{horas}h" + (f" (calidad {calidad}%)" if calidad else "")
            elif d.tipo == "ritmo_cardiaco" and f_str not in ritmo_agregado:
                lpm = d.payload.get("lpm") or d.payload.get("avg_hr") or d.payload.get("bpm")
                if lpm:
                    ritmo_agregado[f_str] = f"{lpm} lpm"

        fechas_unicas = sorted(
            set(list(pasos_agregados.keys()) + list(sueno_agregados.keys()) + list(ritmo_agregado.keys())),
            reverse=True
        )

        for f in fechas_unicas:
            p = pasos_agregados.get(f)
            s = sueno_agregados.get(f)
            r = ritmo_agregado.get(f)
            items = []
            if p:
                items.append(f"pasos={p}")
            if s:
                items.append(f"sueño={s}")
            if r:
                items.append(f"ritmo={r}")
            if items:
                resumen_parts.append(f"{f}: {', '.join(items)}")

        return " | ".join(resumen_parts[:3]) if resumen_parts else None
