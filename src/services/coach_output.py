"""Sanitizacion y guardrails de output del coach."""
from __future__ import annotations

import html as _html
import re

from src.services.crisis import detectar_diagnostico_output

_SAFE_TAGS_RE = re.compile(r"</?(?:b|i|code|pre|blockquote)(?:\s[^>]*)?>")


def sanitize_telegram_html(text: str) -> str:
    """Escapa HTML del output LLM, preservando solo tags seguros de Telegram."""
    parts: list[str] = []
    last = 0
    for m in _SAFE_TAGS_RE.finditer(text):
        parts.append(_html.escape(text[last : m.start()]))
        parts.append(m.group())
        last = m.end()
    parts.append(_html.escape(text[last:]))
    return "".join(parts)


def afirma_registro_sin_tool(output: str, tools: list | None) -> bool:
    """True si el bot afirma haber registrado algo sin invocar tools en el turno."""
    if not output or tools:
        return False
    lower = output.lower()
    frases = (
        "registré",
        "registre",
        "quedó registrado",
        "quedo registrado",
        "ya registré",
        "ya registre",
        "listo, registrado",
        "quedó anotado",
    )
    return any(f in lower for f in frases)


GUARDRAIL_DIAGNOSTICO_MSG = (
    "Note algo en mi respuesta que prefiero no afirmar. Lo correcto es "
    "que un profesional medico/nutricionista/psicologo evalue tu caso. "
    "Sigamos con habitos concretos: que vamos a hacer hoy?"
)

GUARDRAIL_REGISTRO_SIN_TOOL_MSG = (
    "Para registrar eso necesito usar mis herramientas. "
    "Cuentame de nuevo que quieres registrar y lo hago ahora."
)


def aplicar_guardrails_output(output: str, tools: list | None) -> tuple[str, list[str]]:
    """Aplica guardrails regex; retorna (output_final, eventos)."""
    eventos: list[str] = []
    diag = detectar_diagnostico_output(output)
    if diag:
        eventos.append("output_guardrail_diagnostico")
        return GUARDRAIL_DIAGNOSTICO_MSG, eventos
    if afirma_registro_sin_tool(output, tools):
        eventos.append("guardrail_registro_sin_tool")
        return GUARDRAIL_REGISTRO_SIN_TOOL_MSG, eventos
    return output, eventos
