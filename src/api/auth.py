"""Validacion de initData del Mini App de Telegram.

Doc oficial: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Flow:
1. El Mini App envia POST /api/auth/initdata con initData string.
2. Validamos HMAC-SHA256 contra el bot token.
3. Si OK, devolvemos un JWT corto (1 hora) firmado por nosotros.
4. Endpoints de /api/me/* requieren ese JWT en Authorization: Bearer X.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_TTL_SECONDS = 3600


def _validar_init_data(init_data: str) -> dict | None:
    """Valida HMAC del initData de Telegram. Devuelve dict de payload si OK."""
    if not init_data:
        return None
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        return None
    received_hash = parsed.pop("hash", "")
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        settings.telegram_token.get_secret_value().encode(),
        hashlib.sha256,
    ).digest()
    computed = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(computed, received_hash):
        return None
    try:
        auth_date = int(parsed.get("auth_date", "0"))
        if abs(time.time() - auth_date) > 86400:
            return None
    except ValueError:
        return None
    return parsed


def _jwt_secret() -> bytes:
    """Secret separado del admin_token para evitar shared-secret leakage."""
    return settings.jwt_secret.get_secret_value().encode()


def _sign_jwt(uid: int) -> str:
    """JWT HS256 minimalista. Header valida alg='HS256' en verify."""
    import base64

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"uid": uid, "exp": int(time.time()) + JWT_TTL_SECONDS}

    def b64url(obj):
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    body = f"{b64url(header)}.{b64url(payload)}"
    sig = hmac.new(_jwt_secret(), body.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{body}.{sig_b64}"


def verify_jwt(token: str) -> int | None:
    """Valida JWT (firma + alg=HS256 + exp) y devuelve uid o None."""
    import base64

    try:
        body, sig = token.rsplit(".", 1)
        header_b64, payload_b64 = body.split(".", 1)

        padded_h = header_b64 + "=" * (-len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded_h))
        if header.get("alg") != "HS256":
            return None

        expected = hmac.new(_jwt_secret(), body.encode(), hashlib.sha256).digest()
        expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()
        if not hmac.compare_digest(expected_b64, sig):
            return None

        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return int(payload.get("uid"))
    except Exception:
        return None


class InitDataReq(BaseModel):
    init_data: str


class TokenResp(BaseModel):
    jwt: str
    uid: int
    expira_en: int


@router.post("/initdata", response_model=TokenResp)
async def validar_initdata(req: InitDataReq) -> TokenResp:
    """Valida initData del Mini App y devuelve JWT corto."""
    parsed = _validar_init_data(req.init_data)
    if parsed is None:
        raise HTTPException(401, "initData invalido")
    try:
        user_json = parsed.get("user", "{}")
        user = json.loads(user_json)
        uid = int(user.get("id"))
    except Exception:
        raise HTTPException(401, "user invalido en initData")
    return TokenResp(jwt=_sign_jwt(uid), uid=uid, expira_en=JWT_TTL_SECONDS)


async def get_uid_from_token(authorization: str | None = Header(None)) -> int:
    """Dependency: extrae uid del header Authorization: Bearer X."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Bearer token requerido")
    token = authorization[7:]
    uid = verify_jwt(token)
    if uid is None:
        raise HTTPException(401, "Token invalido o expirado")
    return uid
