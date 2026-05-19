"""Tests heuristica de reacciones por keyword."""

from src.telegram.reacciones import _decidir_emoji
from telegram.constants import ReactionEmoji


def test_pr_dispara_fire_big():
    emoji, is_big = _decidir_emoji("Nuevo PR! Rompi mi record en sentadilla")
    assert emoji == ReactionEmoji.FIRE
    assert is_big is True


def test_positivo_basico_fire():
    emoji, _ = _decidir_emoji("Hice 4x8 en banca, listo")
    assert emoji == ReactionEmoji.FIRE


def test_negativo_sad():
    emoji, _ = _decidir_emoji("No entrene hoy, no tengo ganas")
    assert emoji == ReactionEmoji.LOUDLY_CRYING_FACE


def test_lesion_heart():
    emoji, _ = _decidir_emoji("Me lesione la rodilla en el squat")
    assert emoji == ReactionEmoji.RED_HEART


def test_fiesta_clown():
    emoji, _ = _decidir_emoji("Anoche fui de fiesta, hoy guayabo total")
    assert emoji == ReactionEmoji.CLOWN_FACE


def test_neutral_no_reacciona():
    emoji, _ = _decidir_emoji("Hola, como estas?")
    assert emoji is None
