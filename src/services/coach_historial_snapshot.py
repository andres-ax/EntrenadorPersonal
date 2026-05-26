"""Resumen compacto del historial deportivo para modo libre del coach."""
from __future__ import annotations

from datetime import date, timedelta

from src.db.repository import (
    historial_peso,
    listar_prs,
    obtener_compromiso_activo,
    obtener_o_crear_streak,
    obtener_ultimas_sesiones,
)


async def build_historial_snapshot(telegram_id: int, *, max_chars: int = 2400) -> str:
    """Texto denso con entrenos, peso, PRs, sueño y streak (≤~800 tokens)."""
    partes: list[str] = []
    hace_7 = date.today() - timedelta(days=7)

    sesiones = await obtener_ultimas_sesiones(telegram_id, limite=14)
    recientes = [s for s in sesiones if s.fecha and s.fecha >= hace_7]
    if recientes:
        lineas = []
        for s in recientes[:7]:
            ej_count = len(s.ejercicios) if s.ejercicios else 0
            deporte = s.deporte or "entreno"
            lineas.append(f"{s.fecha.isoformat()}: {deporte} ({ej_count} ejercicios)")
        partes.append("Entrenos 7d: " + "; ".join(lineas))
    elif sesiones:
        s = sesiones[0]
        partes.append(f"Ultimo entreno: {s.fecha.isoformat() if s.fecha else '?'} ({s.deporte or 'general'})")
    else:
        partes.append("Entrenos 7d: sin registros")

    pesos = await historial_peso(telegram_id, limit=3)
    if pesos:
        ult = pesos[0]
        partes.append(f"Peso reciente: {ult.peso_kg}kg ({ult.fecha.isoformat() if ult.fecha else '?'})")

    prs = await listar_prs(telegram_id)
    if prs:
        top = prs[:5]
        pr_txt = ", ".join(f"{p.ejercicio} {p.peso_kg}kg×{p.reps}" for p in top)
        partes.append(f"PRs: {pr_txt}")

    try:
        streak = await obtener_o_crear_streak(telegram_id, "entreno")
        partes.append(f"Racha entreno: {streak.dias_actuales} dias")
    except Exception:
        pass

    compromiso = await obtener_compromiso_activo(telegram_id)
    if compromiso:
        partes.append(
            f"Compromiso activo: {compromiso.objetivo_texto[:60]} "
            f"(deadline {compromiso.deadline.isoformat()})"
        )

    texto = " | ".join(partes)
    if len(texto) > max_chars:
        return texto[: max_chars - 3] + "..."
    return texto
