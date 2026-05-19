"""Tests del sistema de tiers (FREE/STARTER/PRO/ELITE/LIFETIME)."""

from __future__ import annotations

import pytest

from src.db.models import PlanSuscripcion
from src.db.repository import PLAN_RANKING


def test_plan_ranking_orden():
    assert PLAN_RANKING[PlanSuscripcion.FREE] == 0
    assert PLAN_RANKING[PlanSuscripcion.STARTER] == 1
    assert PLAN_RANKING[PlanSuscripcion.PRO] == 2
    assert PLAN_RANKING[PlanSuscripcion.ELITE] == 3
    assert PLAN_RANKING[PlanSuscripcion.LIFETIME] == 4


def test_plan_ranking_monotono():
    valores = [PLAN_RANKING[p] for p in PlanSuscripcion]
    assert sorted(valores) == valores


@pytest.mark.parametrize(
    "tier_min,tier_actual,esperado",
    [
        (PlanSuscripcion.FREE, PlanSuscripcion.FREE, True),
        (PlanSuscripcion.STARTER, PlanSuscripcion.FREE, False),
        (PlanSuscripcion.STARTER, PlanSuscripcion.STARTER, True),
        (PlanSuscripcion.PRO, PlanSuscripcion.STARTER, False),
        (PlanSuscripcion.PRO, PlanSuscripcion.PRO, True),
        (PlanSuscripcion.PRO, PlanSuscripcion.ELITE, True),
        (PlanSuscripcion.ELITE, PlanSuscripcion.PRO, False),
        (PlanSuscripcion.PRO, PlanSuscripcion.LIFETIME, True),
        (PlanSuscripcion.ELITE, PlanSuscripcion.LIFETIME, True),
    ],
)
def test_comparacion_tiers(tier_min, tier_actual, esperado):
    cumple = PLAN_RANKING[tier_actual] >= PLAN_RANKING[tier_min]
    assert cumple is esperado
