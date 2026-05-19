"""Autenticacion del panel admin: login email+password -> JWT admin."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time as _t
from typing import Optional

from fastapi import Cookie, Header, HTTPException, Request
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
    """Bcrypt limita a 72 bytes. Truncamos para evitar ValueError."""
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


# Nombre de la cookie HttpOnly que guarda el JWT admin tras el login del panel
# HTML. Se setea desde POST /admin/login y se lee en `get_admin_from_cookie`.
ADMIN_COOKIE_NAME = "admin_jwt"


async def get_admin_from_cookie(
    request: Request,
    admin_jwt: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
) -> dict:
    """Dependency para rutas HTML del panel (src/web/admin_ui.py).

    Lee el JWT desde la cookie HttpOnly `admin_jwt`. Si no existe o es
    invalido, redirige a /admin/login (via 303). Las rutas JSON siguen
    usando `get_admin_from_token` (Authorization Bearer).
    """
    from fastapi.responses import RedirectResponse

    if not admin_jwt:
        raise HTTPException(
            status_code=303,
            detail="Redirect to login",
            headers={"Location": "/admin/login"},
        )
    payload = verify_admin_jwt(admin_jwt)
    if payload is None:
        # Cookie expirada o invalida: limpiarla y redirigir
        resp = RedirectResponse(url="/admin/login", status_code=303)
        resp.delete_cookie(ADMIN_COOKIE_NAME)
        raise HTTPException(
            status_code=303,
            detail="Cookie expirada",
            headers={
                "Location": "/admin/login",
                "Set-Cookie": f"{ADMIN_COOKIE_NAME}=; Max-Age=0; Path=/",
            },
        )
    return payload


async def get_admin_optional(
    admin_jwt: str | None = Cookie(default=None, alias=ADMIN_COOKIE_NAME),
) -> dict | None:
    """Variante que NO redirige; devuelve None si no hay sesion.

    Util para la pagina de login (mostrar boton "ya estas logueado").
    """
    if not admin_jwt:
        return None
    return verify_admin_jwt(admin_jwt)


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    jwt: str
    admin_id: int
    email: str
    rol: str
    expira_en: int


async def seed_admin_si_falta() -> None:
    """Crea el primer admin si la tabla esta vacia y hay env vars de seed.

    Lee `settings.admin_seed_email` y `settings.admin_seed_password`. Si ambos
    estan seteados y todavia no existe ningun admin con ese email, lo crea
    con rol `super`. Idempotente: tras el primer deploy ya no hace nada.

    Pensado para que el primer deploy en Railway quede con un admin listo
    sin requerir ejecutar `scripts/crear_admin.py` manualmente.
    """
    if not settings.admin_seed_email or not settings.admin_seed_password:
        logger.info("Skip seed admin: ADMIN_SEED_EMAIL/PASSWORD no estan seteados")
        return
    email = settings.admin_seed_email.strip().lower()
    password = settings.admin_seed_password.get_secret_value()
    if len(password) < 8:
        logger.warning("Skip seed admin: ADMIN_SEED_PASSWORD muy corto (<8 chars)")
        return
    async with async_session_factory() as session:
        existente = await session.execute(select(Admin).where(Admin.email == email))
        if existente.scalar_one_or_none() is not None:
            logger.info("Seed admin: ya existe admin con email %s, no creo", email)
            return
        nuevo = Admin(
            email=email,
            password_hash=hash_password(password),
            rol=RolAdmin.SUPER,
            activo=True,
        )
        session.add(nuevo)
        await session.commit()
        logger.info("Seed admin creado: email=%s rol=super", email)


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
