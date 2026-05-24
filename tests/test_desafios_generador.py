"""Tests slug y lógica de generador (sin DB)."""
from datetime import date

from src.services.desafios.generador import slug_desafio_dia


def test_slug_desafio_dia():
    slug = slug_desafio_dia(date(2026, 5, 24), "urbano|principiante|perder_grasa")
    assert slug.startswith("2026-05-24-")
    assert "|" not in slug
    assert len(slug) <= 64
