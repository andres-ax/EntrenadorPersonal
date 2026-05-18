"""Autenticacion del panel admin: login email+password -> JWT admin."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time as _t
from typing import Optional

from fastapi import Header, HTTPException
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import select

from src.api.auth import _jwt_secret  # reusa secret JWT
from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import Admin, RolAdmin

logger = logging.getLogger(__name__)

ADMIN_JWT_TTL = 8 * 3600  # 8 horas

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _truncate(plain: str) -> str:
    """bcrypt limita a 72 bytes. Truncamos para evitar ValueError."""
    encoded = plain.encode("utf-8")
    if len(encoded) <= 72:
        return plain
    return encoded[:72].decode("utf-8", "ignore")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(_truncate(plain))


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(_truncate(plain), hashed)
    except Exception:
        return False


def _b64url(obj: dict) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def sign_admin_jwt(admin_id: int, email: str, rol: str) -> str:
    """JWT HS256 con scope=admin para distinguir de los JWT de usuarios."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "scope": "admin",
        "admin_id": admin_id,
        "email": email,
        "rol": rol,
        "exp": int(_t.time()) + ADMIN_JWT_TTL,
    }
    body = f"{_b64url(header)}.{_b64url(payload)}"
    sig = hmac.new(_jwt_secret(), body.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{body}.{sig_b64}"


def verify_admin_jwt(token: str) -> Optional[dict]:
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
        if payload.get("scope") != "admin":
            return None
        if payload.get("exp", 0) < int(_t.time()):
            return None
        return payload
    except Exception:
        return None


async def get_admin_from_token(
    authorization: str | None = Header(None),
    x_admin_token: str | None = Header(None),
) -> dict:
    """Dependency: acepta Bearer JWT (sesion login) o X-Admin-Token (root)."""
    admin_token_settings = settings.admin_token.get_secret_value()
    if x_admin_token and hmac.compare_digest(x_admin_token, admin_token_settings):
        return {
            "scope": "admin",
            "admin_id": 0,
            "email": "root@token",
            "rol": RolAdmin.SUPER.value,
        }
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Auth admin requerida")
    payload = verify_admin_jwt(authorization[7:])
    if payload is None:
        raise HTTPException(401, "Token admin invalido o expirado")
    return payload


async def require_super(admin: dict) -> dict:
    if admin.get("rol") != RolAdmin.SUPER.value:
        raise HTTPException(403, "Requiere rol super")
    return admin


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    jwt: str
    admin_id: int
    email: str
    rol: str
    expira_en: int


async def autenticar_admin(req: LoginRequest) -> LoginResponse:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Admin).where(Admin.email == req.email.lower())
        )
        admin = result.scalar_one_or_none()
        if admin is None or not admin.activo:
            raise HTTPException(401, "Credenciales invalidas")
        if not verify_password(req.password, admin.password_hash):
            raise HTTPException(401, "Credenciales invalidas")
        from datetime import datetime as _dt

        admin.last_login_at = _dt.utcnow()
        await session.commit()
        await session.refresh(admin)
    return LoginResponse(
        jwt=sign_admin_jwt(admin.id, admin.email, admin.rol.value),
        admin_id=admin.id,
        email=admin.email,
        rol=admin.rol.value,
        expira_en=ADMIN_JWT_TTL,
    )
