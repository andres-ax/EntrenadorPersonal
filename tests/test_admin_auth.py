"""Tests del JWT admin + password hashing."""

from __future__ import annotations

from src.api.admin_auth import (
    hash_password,
    sign_admin_jwt,
    verify_admin_jwt,
    verify_password,
)


def test_password_hash_y_verify():
    h = hash_password("mi-contrasena-segura")
    assert verify_password("mi-contrasena-segura", h)
    assert not verify_password("incorrecta", h)


def test_jwt_admin_roundtrip():
    jwt = sign_admin_jwt(admin_id=1, email="x@y.com", rol="super")
    payload = verify_admin_jwt(jwt)
    assert payload is not None
    assert payload["admin_id"] == 1
    assert payload["email"] == "x@y.com"
    assert payload["rol"] == "super"
    assert payload["scope"] == "admin"


def test_jwt_admin_invalido():
    assert verify_admin_jwt("token-invalido") is None
    assert verify_admin_jwt("a.b.c") is None
