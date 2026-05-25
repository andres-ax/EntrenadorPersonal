"""Helpers compartidos para respuestas JWT de la app."""
from __future__ import annotations

from fastapi import Response

from src.api.auth import JWT_APP_TTL_SECONDS, TokenResp, _sign_jwt


def token_resp_app(uid: int, response: Response, profile_complete: bool | None = None) -> TokenResp:
    jwt = _sign_jwt(uid, ttl=JWT_APP_TTL_SECONDS)
    response.set_cookie(
        key="user_jwt",
        value=jwt,
        max_age=JWT_APP_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return TokenResp(
        jwt=jwt,
        uid=uid,
        expira_en=JWT_APP_TTL_SECONDS,
        profile_complete=profile_complete,
    )
