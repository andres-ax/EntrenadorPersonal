"""Tests formato broadcast GM."""
from src.telegram.broadcast_gm import formatear_broadcast_gm


def test_formatear_broadcast_gm_incluye_marca():
    texto = formatear_broadcast_gm("Hola comunidad", admin_email="andres@axsoftware.co")
    assert "MENSAJE DEL EQUIPO" in texto
    assert "Andres" in texto
    assert "Hola comunidad" in texto
    assert "no es el coach IA" in texto


def test_formatear_broadcast_gm_escapa_html():
    texto = formatear_broadcast_gm("<script>alert(1)</script>", gm_nombre="GM")
    assert "<script>" not in texto
    assert "&lt;script&gt;" in texto
