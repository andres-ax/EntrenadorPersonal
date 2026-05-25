"""Tests del modulo de pagos: hash sha256, deteccion duplicados, pricing."""

from __future__ import annotations

from datetime import datetime

from src.db.models import DuracionPago, PlanSuscripcion
from src.services.comprobantes import (
    _parse_fecha,
    _parse_hora,
    _parse_monto,
    sha256_imagen,
)
from src.services.pricing import dias_duracion, formatear_precio, precio_cop


def test_sha256_estable():
    a = sha256_imagen(b"foo")
    b = sha256_imagen(b"foo")
    c = sha256_imagen(b"bar")
    assert a == b
    assert a != c
    assert len(a) == 64


def test_parse_monto():
    assert _parse_monto("14.990", None) == 14990
    assert _parse_monto("$5,000 COP", None) == 5000
    assert _parse_monto("", 12000) == 12000
    assert _parse_monto("", None) == 0


def test_parse_fecha():
    assert _parse_fecha("2026-05-17") == datetime(2026, 5, 17)
    assert _parse_fecha("invalida") is None
    assert _parse_fecha("") is None


def test_parse_hora():
    assert _parse_hora("14:30") is not None
    assert _parse_hora("99:99") is None
    assert _parse_hora("") is None


def test_precio_cop():
    assert precio_cop(PlanSuscripcion.FREE, DuracionPago.MENSUAL) == 0
    assert precio_cop(PlanSuscripcion.STARTER, DuracionPago.MENSUAL) == 5000
    assert precio_cop(PlanSuscripcion.PRO, DuracionPago.MENSUAL) == 14990
    pro_anual = precio_cop(PlanSuscripcion.PRO, DuracionPago.ANUAL)
    assert pro_anual == 14990 * 12 - (14990 * 12 * 20 // 100)
    assert precio_cop(PlanSuscripcion.LIFETIME, DuracionPago.LIFETIME) == 399000


def test_dias_duracion():
    assert dias_duracion(PlanSuscripcion.STARTER, DuracionPago.MENSUAL) == 30
    assert dias_duracion(PlanSuscripcion.PRO, DuracionPago.ANUAL) == 365
    assert dias_duracion(PlanSuscripcion.LIFETIME, DuracionPago.LIFETIME) == 36500


def test_formatear_precio():
    assert formatear_precio(5000) == "$5.000"
    assert formatear_precio(14990) == "$14.990"
    assert formatear_precio(399000) == "$399.000"
