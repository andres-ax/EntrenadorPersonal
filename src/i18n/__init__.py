"""i18n basico para strings de bot (comandos, descripciones, comandos del menu).

Diseno minimo: dict[idioma][key] -> texto.
Por ahora solo es OPT-IN para textos del bot_setup. El prompt del coach maneja
idioma via REGLA #5 (tono-aware) detectando lang_code en el contexto inyectado.
"""
from __future__ import annotations

import logging
from typing import Literal

logger = logging.getLogger(__name__)

LangCode = Literal["es", "en", "pt"]
DEFAULT_LANG: LangCode = "es"


STRINGS: dict[str, dict[str, str]] = {
    "es": {
        "bot.name": "EntrenadorAX",
        "bot.short_desc": "Coach AI que no te deja excusas. Entreno, comida, sueno, peso.",
        "bot.desc": (
            "Soy EntrenadorAX, tu coach personal con IA dentro de Telegram.\n\n"
            "Te ayudo a registrar entrenamientos, comidas, sueno y peso conversando. "
            "Te recuerdo cuando flojeas con el tono que elijas. "
            "Solo escribeme. /start para empezar."
        ),
        "welcome.back": "Bienvenido de vuelta, {nombre}!",
    },
    "en": {
        "bot.name": "EntrenadorAX",
        "bot.short_desc": "AI coach that holds you accountable. Workouts, nutrition, sleep, weight.",
        "bot.desc": (
            "I am EntrenadorAX, your AI personal coach inside Telegram.\n\n"
            "I help you log workouts, meals, sleep and weight via chat. "
            "I remind you when you slack with the tone you choose. "
            "Just text me. /start to begin."
        ),
        "welcome.back": "Welcome back, {nombre}!",
    },
    "pt": {
        "bot.name": "EntrenadorAX",
        "bot.short_desc": "Coach IA que cobra. Treinos, comida, sono, peso.",
        "bot.desc": (
            "Sou o EntrenadorAX, seu coach pessoal com IA dentro do Telegram.\n\n"
            "Ajudo voce a registrar treinos, comidas, sono e peso conversando. "
            "Te lembro quando voce afrouxa com o tom que voce escolher. "
            "Basta me escrever. /start para comecar."
        ),
        "welcome.back": "Bem-vindo de volta, {nombre}!",
    },
}


def t(key: str, lang: str | None = None, **kwargs) -> str:
    """Traduce key con fallback a espanol."""
    lang_code = (lang or DEFAULT_LANG).lower()[:2]
    if lang_code not in STRINGS:
        lang_code = DEFAULT_LANG
    text = STRINGS[lang_code].get(key) or STRINGS[DEFAULT_LANG].get(key) or key
    try:
        return text.format(**kwargs) if kwargs else text
    except KeyError:
        return text


def detectar_idioma(language_code: str | None) -> str:
    """Detecta el idioma del language_code de Telegram."""
    if not language_code:
        return DEFAULT_LANG
    code = language_code.lower()[:2]
    return code if code in STRINGS else DEFAULT_LANG
