"""setMessageReaction heuristica por keywords. Cero tokens IA, personalidad instantanea."""

from __future__ import annotations

import logging
import re

import telegram.error
from telegram import Message
from telegram.constants import ReactionEmoji
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


_POSITIVOS = re.compile(
    r"\b(entren[ée]|hice|listo|hecho|termin[eé]|pr|record|nuevo peso|baj[eé]|"
    r"sub[ií]|complet[eé]|logr[eé]|ya\s+estuvo)\b",
    re.IGNORECASE,
)
_NEGATIVOS = re.compile(
    r"\b(no\s+entren|no\s+hice|me\s+salt[eé]|no\s+tengo\s+ganas|no\s+pude|fall[eé]|"
    r"no\s+fui|cansad[oa]|flojo|flojera|no\s+me\s+pari|hue[ñn]a)\b",
    re.IGNORECASE,
)
_LESION = re.compile(
    r"\b(lesion|lesione|lesionad|me\s+duele|dolor\s|fract|esguinc|"
    r"tor(c|s)i|inflamad|hinchad)\b",
    re.IGNORECASE,
)
_FIESTA = re.compile(
    r"\b(fiesta|borrach[oa]|trasnoch|guayabo|cruda|hangover|rumba|tomamos\s+mucho)\b",
    re.IGNORECASE,
)
_SUENO_BIEN = re.compile(
    r"\b(dorm[ií]\s+\d|dorm[ií]\s+rico|dorm[ií]\s+bien|descans[eé]|" r"recuperad[oa])\b",
    re.IGNORECASE,
)
_PR_PROBABLE = re.compile(
    r"\b(rompi|nuevo\s+pr|record\s+personal|primera\s+vez|jam[aá]s\s+habia)\b",
    re.IGNORECASE,
)
_CRISIS = re.compile(
    r"\b(quiero\s+morir|no\s+aguanto\s+mas|me\s+odio|no\s+como\s+hace|"
    r"vomit[eé]|no\s+puedo\s+m[aá]s)\b",
    re.IGNORECASE,
)


def _decidir_emoji(texto: str) -> tuple[ReactionEmoji | None, bool]:
    """Devuelve (emoji o None, is_big)."""
    if not texto:
        return None, False
    if _CRISIS.search(texto):
        return ReactionEmoji.RED_HEART, True
    if _LESION.search(texto):
        return ReactionEmoji.RED_HEART, False
    if _NEGATIVOS.search(texto):
        return ReactionEmoji.LOUDLY_CRYING_FACE, False
    if _PR_PROBABLE.search(texto):
        return ReactionEmoji.FIRE, True
    if _FIESTA.search(texto):
        return ReactionEmoji.CLOWN_FACE, False
    if _SUENO_BIEN.search(texto):
        return ReactionEmoji.HIGH_VOLTAGE_SIGN, False
    if _POSITIVOS.search(texto):
        return ReactionEmoji.FIRE, False
    return None, False


async def reaccionar(message: Message, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Reacciona al mensaje del user segun keywords. Best-effort, no falla nunca."""
    emoji, is_big = _decidir_emoji(message.text or "")
    if emoji is None:
        return
    try:
        await ctx.bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[emoji],
            is_big=is_big,
        )
    except telegram.error.BadRequest as e:
        logger.debug("Reaction rechazada: %s", e)
    except Exception:
        logger.exception("Error reaccionando al mensaje")
