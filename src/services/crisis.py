"""Clasificador de crisis basado en keywords. INDEPENDIENTE del LLM principal.

Basado en research/tough-love-coaching-framework.md seccion 6.

Niveles:
- 1 = URGENTE: ideacion suicida, autolesion, "no puedo mas". Respuesta inmediata
      + pausa total 7 dias + log + notificar admin.
- 2 = ALTA PREOCUPACION: TCA explicito (vomito, ayuno, atracon), depresion clinica,
      abuso. Tono empatico + derivar a profesional.
- 3 = VIGILANCIA: sobreentrenamiento, amenorrea, dolor agudo persistente. Sugerir
      consulta sin bloquear conversacion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import settings


_NIVEL_1 = re.compile(
    r"\b(quiero\s+morir|me\s+quiero\s+matar|no\s+aguanto\s+m[aá]s|no\s+puedo\s+m[aá]s|"
    r"me\s+voy\s+a\s+matar|suicid|autolesion|me\s+corto|me\s+lastimo|"
    r"no\s+tiene\s+sentido\s+seguir|no\s+vale\s+la\s+pena\s+vivir|"
    r"acabar\s+con\s+todo|terminar\s+con\s+mi\s+vida)\b",
    re.IGNORECASE,
)

_NIVEL_2_TCA = re.compile(
    r"\b(vomit[eé]|provoqu[eé]\s+vomit|laxantes|diuretico|atracon|atraqu[eé]|"
    r"no\s+he\s+comido\s+(en|hace)\s+\d|llevo\s+\d+\s+dias\s+sin\s+comer|"
    r"ayuno\s+de\s+\d+\s+horas|comi\s+a\s+escondidas|comer\s+en\s+secreto|"
    r"me\s+da\s+asco\s+comer|odio\s+mi\s+cuerpo|me\s+veo\s+gord|"
    r"contar\s+cada\s+caloria\s+me\s+obsesi|tengo\s+anorexia|tengo\s+bulimia)\b",
    re.IGNORECASE,
)

_NIVEL_2_DEPRE = re.compile(
    r"\b(estoy\s+deprimid|no\s+tengo\s+ganas\s+de\s+nada|llevo\s+semanas\s+sin\s+salir|"
    r"todo\s+me\s+da\s+igual|me\s+siento\s+vacio|no\s+veo\s+salida|"
    r"crisis\s+de\s+ansiedad|ataque\s+de\s+panico|panic\s+attack)\b",
    re.IGNORECASE,
)

_NIVEL_3 = re.compile(
    r"\b(amenorrea|sin\s+regla\s+(hace|desde)|fractura\s+por\s+estres|"
    r"me\s+lastim[eé]\s+entrenando|dolor\s+(fuerte|agudo)\s+(en|de)|"
    r"entren[oó]\s+(\d{3}|m[aá]s\s+de\s+\d{2})\s+horas|"
    r"no\s+puedo\s+dejar\s+de\s+entrenar)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CrisisDetected:
    nivel: int
    keywords: list[str]
    mensaje_contenedor: str
    lineas_crisis: str


LINEAS_POR_PAIS: dict[str, str] = {
    "CO": (
        "<b>Lineas en Colombia:</b>\n"
        "- 192 MinSalud (nacional)\n"
        "- 106 Bogota / WhatsApp 300 754 8933\n"
        "- 123 emergencias"
    ),
    "MX": (
        "<b>Lineas en Mexico:</b>\n"
        "- 800 911 2000 SAPTEL\n"
        "- 911 emergencias"
    ),
    "AR": (
        "<b>Lineas en Argentina:</b>\n"
        "- 135 (CABA) / 0800-345-1435 (nacional)\n"
        "- 911 emergencias"
    ),
    "ES": (
        "<b>Lineas en Espana:</b>\n"
        "- 024 (oficial MinSalud, gratuito 24/7)\n"
        "- 717 003 717 (Telefono Esperanza)\n"
        "- 112 emergencias"
    ),
    "PE": (
        "<b>Lineas en Peru:</b>\n"
        "- 113 opcion 5 MinSal\n"
        "- ANAR 0800-2-2210"
    ),
    "CL": (
        "<b>Lineas en Chile:</b>\n"
        "- *4141 Salud Responde\n"
        "- 600 360 7777 Linea Libre"
    ),
    "US": (
        "<b>Lineas en US (espanol disponible):</b>\n"
        "- 988 Suicide & Crisis Lifeline"
    ),
}

_LINEAS_FALLBACK = (
    "Por favor marca el numero nacional de emergencias de tu pais o busca "
    "'linea de crisis [tu pais]' en internet."
)


def _lineas_pais(pais: str | None) -> str:
    if not pais:
        return _LINEAS_FALLBACK
    return LINEAS_POR_PAIS.get(pais.upper(), _LINEAS_FALLBACK)


def _mensaje_nivel_1(pais: str | None) -> str:
    return (
        "Lo que me cuentas es muy importante. <b>No estas solo/a</b> y aqui hay "
        "ayuda profesional disponible las 24 horas:\n\n"
        f"{_lineas_pais(pais)}\n\n"
        "Voy a pausar los recordatorios <b>7 dias</b>. Mientras tanto, "
        "por favor contacta a alguien de tu red cercana o llama a una de "
        "esas lineas. Volvemos cuando estes mejor."
    )


def _mensaje_nivel_2(pais: str | None) -> str:
    return (
        "Gracias por contarmelo. Esto que vives merece <b>acompanamiento "
        "profesional</b> (psicologia, nutricion clinica o medico segun el caso). "
        "Yo soy un coach de habitos, no puedo tratar esto, pero quiero ayudarte "
        "a dar el siguiente paso:\n\n"
        f"{_lineas_pais(pais)}\n\n"
        "Sigo aqui para acompanarte en lo cotidiano con respeto. Si quieres, "
        "pausa mis recordatorios con /pausa 7."
    )


def _mensaje_nivel_3(pais: str | None) -> str:
    return (
        "Lo que mencionas merece evaluacion <b>profesional</b> antes de seguir "
        "presionando con entrenamiento. Por favor consulta con tu medico/fisio/"
        "ginecologa/o nutricionista. Mientras tanto bajamos la intensidad."
    )


def detectar(texto: str, pais: str | None = "CO") -> CrisisDetected | None:
    """Analiza texto. Devuelve CrisisDetected si encuentra red flag."""
    if not texto:
        return None

    nivel_1_match = _NIVEL_1.findall(texto)
    if nivel_1_match:
        return CrisisDetected(
            nivel=1,
            keywords=list(set(nivel_1_match)),
            mensaje_contenedor=_mensaje_nivel_1(pais),
            lineas_crisis=_lineas_pais(pais),
        )

    nivel_2_tca = _NIVEL_2_TCA.findall(texto)
    nivel_2_dep = _NIVEL_2_DEPRE.findall(texto)
    if nivel_2_tca or nivel_2_dep:
        keys = [k for k in (nivel_2_tca + nivel_2_dep) if k]
        return CrisisDetected(
            nivel=2,
            keywords=list({str(k) for k in keys}),
            mensaje_contenedor=_mensaje_nivel_2(pais),
            lineas_crisis=_lineas_pais(pais),
        )

    nivel_3_match = _NIVEL_3.findall(texto)
    if nivel_3_match:
        keys = [k for k in nivel_3_match if k]
        return CrisisDetected(
            nivel=3,
            keywords=list({str(k) for k in keys}),
            mensaje_contenedor=_mensaje_nivel_3(pais),
            lineas_crisis=_lineas_pais(pais),
        )

    return None


_DIAGNOSTICOS_PROHIBIDOS = re.compile(
    r"\b(tienes\s+(anorexia|bulimia|atracon|depresion|diabetes|hipertension|"
    r"obesidad|trastorno|tdah|ansiedad\s+generalizada|TOC|PTSD)|"
    r"sufres\s+de\s+(anorexia|bulimia|depresion|diabetes)|"
    r"estas\s+(deprimid|enferm)|"
    r"diagnostico\s+(de|es)\s+(anorexia|bulimia|depresion))\b",
    re.IGNORECASE,
)


def detectar_diagnostico_output(texto: str) -> list[str]:
    """Anti-diagnostico en el output del agente. Devuelve frases ofensoras."""
    if not texto:
        return []
    return _DIAGNOSTICOS_PROHIBIDOS.findall(texto)
