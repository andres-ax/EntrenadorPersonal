"""Tests de cuotas Realtime por tier."""

from __future__ import annotations

from src.db.models import PlanSuscripcion
from src.realtime.cuotas import CUOTAS_MIN_POR_TIER


def test_cuotas_consistentes_con_tiers():
    assert CUOTAS_MIN_POR_TIER[PlanSuscripcion.FREE] == 0
    assert CUOTAS_MIN_POR_TIER[PlanSuscripcion.STARTER] == 5
    assert CUOTAS_MIN_POR_TIER[PlanSuscripcion.PRO] == 30
    assert CUOTAS_MIN_POR_TIER[PlanSuscripcion.ELITE] == 120
    assert CUOTAS_MIN_POR_TIER[PlanSuscripcion.LIFETIME] == 120


def test_cuotas_crecientes_por_tier():
    valores = [
        CUOTAS_MIN_POR_TIER[p]
        for p in [
            PlanSuscripcion.FREE,
            PlanSuscripcion.STARTER,
            PlanSuscripcion.PRO,
            PlanSuscripcion.ELITE,
        ]
    ]
    assert sorted(valores) == valores
