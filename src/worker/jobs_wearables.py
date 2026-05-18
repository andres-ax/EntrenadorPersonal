"""Jobs arq para sync de wearables y refresh de tokens."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx
from sqlalchemy import select

from src.db.connection import async_session_factory
from src.db.models import DatosWearableRaw, IntegracionWearable
from src.services.crypto import decrypt_str, encrypt_str

logger = logging.getLogger(__name__)


WHOOP_API = "https://api.prod.whoop.com/developer/v1"
STRAVA_API = "https://www.strava.com/api/v3"


async def sync_single_integration(ctx, integracion_id: int) -> int:
    """Sync inmediato de una integracion. Devuelve N items insertados."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(IntegracionWearable).where(
                IntegracionWearable.id == integracion_id
            )
        )
        integ = result.scalar_one_or_none()
        if integ is None:
            return 0

        if integ.expires_at and integ.expires_at < datetime.utcnow() + timedelta(minutes=5):
            await _refrescar_token(integ)
            await session.commit()
            await session.refresh(integ)

        access = decrypt_str(integ.access_token or "")
        if not access:
            integ.sync_status = "error"
            integ.error_msg = "token_invalido"
            await session.commit()
            return 0

        try:
            if integ.proveedor == "whoop":
                items = await _sync_whoop(integ, access)
            elif integ.proveedor == "strava":
                items = await _sync_strava(integ, access)
            else:
                items = []
        except Exception as e:
            logger.exception("Error sync %s integ=%s", integ.proveedor, integ.id)
            integ.sync_status = "error"
            integ.error_msg = str(e)[:200]
            await session.commit()
            return 0

        insertados = 0
        for item in items:
            existing = await session.execute(
                select(DatosWearableRaw).where(
                    DatosWearableRaw.integracion_id == integ.id,
                    DatosWearableRaw.external_id == item["external_id"],
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            raw = DatosWearableRaw(
                integracion_id=integ.id,
                tipo=item["tipo"],
                external_id=item["external_id"],
                fecha=item["fecha"],
                payload=item["payload"],
            )
            session.add(raw)
            insertados += 1

        integ.last_sync_at = datetime.utcnow()
        integ.sync_status = "ok"
        integ.error_msg = ""
        await session.commit()
        return insertados


async def sync_all_active_integrations(ctx) -> int:
    """Cron 4h: sync todas las integraciones activas."""
    async with async_session_factory() as session:
        result = await session.execute(select(IntegracionWearable))
        ids = [i.id for i in result.scalars().all()]
    total = 0
    for iid in ids:
        try:
            total += await sync_single_integration(ctx, iid)
        except Exception:
            logger.exception("Error en sync masivo integ=%s", iid)
    logger.info("Sync masivo: %s items insertados de %s integraciones", total, len(ids))
    return total


async def refresh_tokens_expirados(ctx) -> int:
    """Cron diario 6am: refresca tokens que expiren en proximas 12h."""
    cutoff = datetime.utcnow() + timedelta(hours=12)
    refrescados = 0
    async with async_session_factory() as session:
        result = await session.execute(
            select(IntegracionWearable).where(
                IntegracionWearable.expires_at.is_not(None),
                IntegracionWearable.expires_at < cutoff,
            )
        )
        integraciones = list(result.scalars().all())
        for integ in integraciones:
            try:
                if await _refrescar_token(integ):
                    refrescados += 1
            except Exception:
                logger.exception("Error refresh integ=%s", integ.id)
        await session.commit()
    logger.info("Refrescados %s tokens", refrescados)
    return refrescados


async def _refrescar_token(integ: IntegracionWearable) -> bool:
    """Llama al endpoint de refresh del proveedor y actualiza tokens en el objeto."""
    refresh = decrypt_str(integ.refresh_token or "")
    if not refresh:
        return False
    token_url = _get_token_url(integ.proveedor)
    cid, csec = _get_client_credentials(integ.proveedor)
    if not (cid and csec and token_url):
        return False
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh,
        "client_id": cid,
        "client_secret": csec,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(token_url, data=payload)
            r.raise_for_status()
            tokens = r.json()
    except Exception:
        logger.exception("Refresh fallo %s integ=%s", integ.proveedor, integ.id)
        return False

    integ.access_token = encrypt_str(tokens.get("access_token", ""))
    if tokens.get("refresh_token"):
        integ.refresh_token = encrypt_str(tokens["refresh_token"])
    expires_in = int(tokens.get("expires_in", 3600))
    integ.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
    return True


def _get_token_url(proveedor: str) -> Optional[str]:
    urls = {
        "whoop": "https://api.prod.whoop.com/oauth/oauth2/token",
        "strava": "https://www.strava.com/oauth/token",
        "google_fit": "https://oauth2.googleapis.com/token",
        "garmin": "https://connectapi.garmin.com/oauth-service/oauth/access_token",
    }
    return urls.get(proveedor)


def _get_client_credentials(proveedor: str) -> tuple[str, str]:
    cid = os.environ.get(f"{proveedor.upper()}_CLIENT_ID", "")
    csec = os.environ.get(f"{proveedor.upper()}_CLIENT_SECRET", "")
    return cid, csec


async def _sync_whoop(integ: IntegracionWearable, access: str) -> list[dict]:
    """Descarga workouts + recovery + sleep de Whoop."""
    items = []
    desde = (integ.last_sync_at or datetime.utcnow() - timedelta(days=14)).isoformat() + "Z"
    headers = {"Authorization": f"Bearer {access}"}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        for tipo, url in [
            ("workout", f"{WHOOP_API}/activity/workout"),
            ("sleep", f"{WHOOP_API}/activity/sleep"),
            ("recovery", f"{WHOOP_API}/recovery"),
        ]:
            try:
                r = await client.get(url, params={"start": desde, "limit": 25})
                r.raise_for_status()
                data = r.json().get("records", [])
            except Exception:
                logger.exception("Whoop %s fallo", tipo)
                continue
            for record in data:
                fecha_iso = (
                    record.get("created_at")
                    or record.get("start")
                    or datetime.utcnow().isoformat()
                )
                try:
                    fecha = datetime.fromisoformat(fecha_iso.replace("Z", "+00:00")).date()
                except (ValueError, TypeError):
                    fecha = datetime.utcnow().date()
                items.append(
                    {
                        "tipo": tipo,
                        "external_id": f"whoop:{tipo}:{record.get('id')}",
                        "fecha": fecha,
                        "payload": record,
                    }
                )
    return items


async def _sync_strava(integ: IntegracionWearable, access: str) -> list[dict]:
    """Descarga actividades de Strava."""
    items = []
    desde_ts = int(
        (integ.last_sync_at or datetime.utcnow() - timedelta(days=14)).timestamp()
    )
    headers = {"Authorization": f"Bearer {access}"}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        try:
            r = await client.get(
                f"{STRAVA_API}/athlete/activities",
                params={"after": desde_ts, "per_page": 30},
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            logger.exception("Strava activities fallo")
            return []
        for act in data:
            try:
                fecha = datetime.fromisoformat(
                    (act.get("start_date") or "").replace("Z", "+00:00")
                ).date()
            except (ValueError, TypeError):
                fecha = datetime.utcnow().date()
            items.append(
                {
                    "tipo": "workout",
                    "external_id": f"strava:{act.get('id')}",
                    "fecha": fecha,
                    "payload": act,
                }
            )
    return items
