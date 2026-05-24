"""Formato visual distintivo para broadcasts del admin (estilo GM)."""
from __future__ import annotations

import html
import re


def _nombre_desde_email(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    local = email.split("@", 1)[0].strip()
    local = re.sub(r"[._-]+", " ", local)
    return local.title() if local else None


def formatear_broadcast_gm(
    mensaje: str,
    *,
    admin_email: str | None = None,
    gm_nombre: str | None = None,
) -> str:
    """Envuelve el mensaje del admin para distinguirlo del coach IA en Telegram."""
    nombre = (gm_nombre or _nombre_desde_email(admin_email) or "Equipo EntrenadorAX").strip()
    cuerpo = html.escape(mensaje.strip())
    return (
        "🎮 <b>━━━ MENSAJE DEL EQUIPO ━━━</b>\n"
        f"📢 <i>De {html.escape(nombre)} · EntrenadorAX</i>\n\n"
        f"{cuerpo}\n\n"
        "<i>— Mensaje humano del equipo, no es el coach IA.</i>"
    )
