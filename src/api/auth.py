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

from fastapi import APIRouter, Cookie, Header, HTTPException, Response
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


class CodigoWebReq(BaseModel):
    codigo: str


@router.post("/codigo", response_model=TokenResp)
async def validar_codigo_web(req: CodigoWebReq, response: Response) -> TokenResp:
    """Login web del deportista via codigo de 6 digitos generado por el bot.

    Flujo:
    1. Usuario manda /codigo_web al bot.
    2. Bot genera codigo, lo guarda en Redis con TTL 15 min.
    3. Usuario pega el codigo en /login (landing).
    4. Este endpoint valida, consume el codigo (single-use) y setea
       cookie HttpOnly `user_jwt`.

    Auth alternativa al `/api/auth/initdata` (que requiere abrir el mini
    app desde Telegram con `initData`). El codigo permite entrar desde
    cualquier navegador.
    """
    from src.services.codigo_web import validar_y_consumir

    uid = await validar_y_consumir(req.codigo)
    if uid is None:
        raise HTTPException(401, "Codigo invalido o expirado")
    jwt = _sign_jwt(uid)
    response.set_cookie(
        key="user_jwt",
        value=jwt,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",  # lax para que sobreviva navegacion same-site
        path="/",
    )
    return TokenResp(jwt=jwt, uid=uid, expira_en=JWT_TTL_SECONDS)


@router.post("/initdata", response_model=TokenResp)
async def validar_initdata(req: InitDataReq, response: Response) -> TokenResp:
    """Valida initData del Mini App y devuelve JWT corto.

    Tambien setea una cookie HttpOnly `user_jwt` que las paginas HTML del
    mini app (/app/*) leen para autenticar al usuario sin pasar el token
    por JS / localStorage. El JSON response se mantiene por compatibilidad
    con clientes que ya envian el JWT en el header Authorization.
    """
    parsed = _validar_init_data(req.init_data)
    if parsed is None:
        raise HTTPException(401, "initData invalido")
    try:
        user_json = parsed.get("user", "{}")
        user = json.loads(user_json)
        uid = int(user.get("id"))
    except Exception:
        raise HTTPException(401, "user invalido en initData")
    jwt = _sign_jwt(uid)
    # Cookie para las paginas HTML del mini app (Telegram WebApp).
    # SameSite=None porque Telegram abre la web app en un iframe cross-site.
    # Secure obligatorio para SameSite=None.
    response.set_cookie(
        key="user_jwt",
        value=jwt,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    return TokenResp(jwt=jwt, uid=uid, expira_en=JWT_TTL_SECONDS)


async def get_uid_from_token(
    authorization: str | None = Header(None),
    user_jwt: str | None = Cookie(default=None, alias="user_jwt"),
) -> int:
    """Dependency: extrae uid del Authorization: Bearer X o cookie user_jwt.

    Acepta DOS fuentes para que `/api/me/*` funcione tanto desde:
    - Telegram Mini App (legacy: localStorage + Bearer header).
    - Panel web HTML (cookie HttpOnly seteada por /login/deportista o
      /api/auth/codigo).
    """
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif user_jwt:
        token = user_jwt
    if not token:
        raise HTTPException(401, "Auth requerida (Bearer header o cookie user_jwt)")
    uid = verify_jwt(token)
    if uid is None:
        raise HTTPException(401, "Token invalido o expirado")
    return uid


# --- Magic link (auth web alternativa) ---


import secrets as _secrets  # noqa: E402
from datetime import datetime as _dt, timedelta as _td  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import select as _select  # noqa: E402

from src.db.connection import async_session_factory as _afs  # noqa: E402
from src.db.models import MagicLink, Usuario  # noqa: E402


class MagicLinkReq(BaseModel):
    email: str


class MagicLinkResp(BaseModel):
    ok: bool
    message: str


@router.post("/magic-link", response_model=MagicLinkResp)
async def crear_magic_link(req: MagicLinkReq) -> MagicLinkResp:
    """Genera magic link + envia por Resend (si key seteada) o log."""
    token = _secrets.token_urlsafe(48)
    expires_at = _dt.utcnow() + _td(minutes=15)
    email = req.email.lower().strip()
    async with _afs() as session:
        ml = MagicLink(
            token=token, email=email, expires_at=expires_at
        )
        session.add(ml)
        await session.commit()

    landing_url = str(settings.landing_url or settings.miniapp_url or "").rstrip("/")
    verify_url = f"{landing_url}/auth/verify?token={token}" if landing_url else None

    if settings.resend_api_key and verify_url:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": "EntrenadorAX <entrenadorax@axsoftware.codes>",
                        "to": [email],
                        "subject": "Tu link de acceso a EntrenadorAX",
                        "html": (
                            f"<p>Hola,</p>"
                            f"<p>Aqui esta tu link para entrar a EntrenadorAX:</p>"
                            f"<p><a href='{verify_url}'>Entrar</a></p>"
                            f"<p>Expira en 15 minutos.</p>"
                            f"<p>Si no fuiste tu, ignora este email.</p>"
                        ),
                    },
                )
        except Exception:
            logger.exception("Error enviando magic link via Resend")
    else:
        token_prefix = (token or "")[:8]
        logger.info(
            "Magic link generado email=%s token_prefix=%s... "
            "(Resend no configurado; ver DB para detalle)",
            email,
            token_prefix,
        )

    return MagicLinkResp(
        ok=True,
        message="Si el email es valido, recibiras un link en breve.",
    )


@router.get("/verify", response_model=TokenResp)
async def verificar_magic_link(token: str, response: Response) -> TokenResp:
    """Verifica magic link + devuelve JWT + setea cookie user_jwt."""
    if not token:
        raise HTTPException(400, "token requerido")
    async with _afs() as session:
        ml_q = await session.execute(
            _select(MagicLink).where(MagicLink.token == token)
        )
        ml = ml_q.scalar_one_or_none()
        if ml is None:
            raise HTTPException(401, "magic link invalido")
        if ml.used_at is not None:
            raise HTTPException(401, "magic link ya usado")
        if ml.expires_at < _dt.utcnow():
            raise HTTPException(401, "magic link expirado")

        user_q = await session.execute(
            _select(Usuario).where(Usuario.email == ml.email)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            user = Usuario(
                telegram_id=-int(_secrets.randbits(32)),  # placeholder uid si solo web
                email=ml.email,
                email_verified_at=_dt.utcnow(),
                auth_method="email",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            user.email_verified_at = _dt.utcnow()
            if user.auth_method == "telegram":
                user.auth_method = "both"
        ml.used_at = _dt.utcnow()
        await session.commit()
        uid = user.telegram_id
    jwt = _sign_jwt(uid)
    response.set_cookie(
        key="user_jwt",
        value=jwt,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return TokenResp(jwt=jwt, uid=uid, expira_en=JWT_TTL_SECONDS)
