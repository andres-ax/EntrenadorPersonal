"""Scoring en tiempo real para desafíos activos."""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from src.db.connection import async_session_factory
from src.db.models import Desafio, DesafioParticipante, DesafioProgresoLog, Usuario
from src.services.comunidad import recalcular_ranking
from src.timezone_utils import fecha_hoy_usuario

logger = logging.getLogger(__name__)

METRICA_EVENTO: dict[str, str] = {
    "minutos_entreno": "minutos_entreno",
    "volumen_kg": "volumen_kg",
    "sesiones": "sesiones",
    "comidas": "comidas",
    "agua_ml": "agua_ml",
}


async def registrar_progreso(
    telegram_id: int,
    evento: str,
    valor: float,
    *,
    acumular: bool = True,
) -> list[dict]:
    """Actualiza participaciones activas cuya métrica coincide con el evento."""
    metrica = METRICA_EVENTO.get(evento, evento)
    hoy = await fecha_hoy_usuario(telegram_id)
    resultados: list[dict] = []

    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = user_q.scalar_one_or_none()
        if user is None:
            return resultados

        participaciones_q = await session.execute(
            select(DesafioParticipante, Desafio)
            .join(Desafio, Desafio.id == DesafioParticipante.desafio_id)
            .where(
                DesafioParticipante.usuario_id == user.id,
                Desafio.fecha_inicio <= hoy,
                Desafio.fecha_fin >= hoy,
                Desafio.estado == "activo",
                Desafio.metrica == metrica,
            )
        )
        rows = participaciones_q.all()

        for participante, desafio in rows:
            delta = valor
            if acumular:
                nuevo = participante.valor_actual + valor
            else:
                nuevo = max(participante.valor_actual, valor)

            if desafio.metrica == "agua_ml":
                # valor es ratio 0-1 vs objetivo diario
                cap = desafio.meta_valor
                nuevo = min(nuevo, cap)
            elif desafio.meta_valor > 0:
                nuevo = min(nuevo, desafio.meta_valor * 1.5)

            if nuevo == participante.valor_actual:
                continue

            participante.valor_actual = nuevo
            log = DesafioProgresoLog(
                desafio_id=desafio.id,
                usuario_id=user.id,
                evento=evento,
                delta=delta,
                valor_despues=nuevo,
            )
            session.add(log)
            resultados.append(
                {
                    "desafio_id": desafio.id,
                    "slug": desafio.slug,
                    "titulo": desafio.titulo,
                    "valor": nuevo,
                    "meta": desafio.meta_valor,
                    "meta_alcanzada": desafio.meta_valor > 0 and nuevo >= desafio.meta_valor,
                }
            )

        if resultados:
            await session.commit()
            for r in resultados:
                await recalcular_ranking(r["desafio_id"])

    return resultados


async def _desafio_progress_safe(
    telegram_id: int,
    evento: str,
    valor: float,
    *,
    acumular: bool = True,
) -> None:
    try:
        await registrar_progreso(telegram_id, evento, valor, acumular=acumular)
    except Exception:
        logger.exception(
            "desafio_progress fallo uid=%s evento=%s",
            telegram_id,
            evento,
            exc_info=True,
        )


async def actualizar_progreso_comidas(telegram_id: int) -> None:
    from sqlalchemy import func

    from src.db.models import Comida
    from src.timezone_utils import fecha_hoy_usuario

    hoy = await fecha_hoy_usuario(telegram_id)
    async with async_session_factory() as session:
        uq = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        user = uq.scalar_one_or_none()
        if user is None:
            return
        cq = await session.execute(
            select(func.count(Comida.id)).where(
                Comida.usuario_id == user.id,
                Comida.fecha == hoy,
            )
        )
        total = int(cq.scalar() or 0)
    await _desafio_progress_safe(telegram_id, "comidas", float(total), acumular=False)


async def actualizar_progreso_agua(telegram_id: int) -> None:
    from src.services.hidratacion import consumo_hoy_ml, objetivo_ml

    consumo = await consumo_hoy_ml(telegram_id)
    obj = await objetivo_ml(telegram_id)
    ratio = (consumo / obj) if obj > 0 else 0.0
    await _desafio_progress_safe(telegram_id, "agua_ml", ratio, acumular=False)


async def actualizar_progreso_sesion(telegram_id: int, sesion) -> None:
    """Actualiza métricas de entreno al cerrar o registrar sesión."""
    duracion = float(sesion.duracion_min or 0)
    volumen = 0.0
    for ej in getattr(sesion, "ejercicios", []) or []:
        volumen += (ej.peso_kg or 0) * (ej.series or 0) * (ej.reps or 0)
    await _desafio_progress_safe(telegram_id, "minutos_entreno", duracion, acumular=True)
    if volumen > 0:
        await _desafio_progress_safe(telegram_id, "volumen_kg", volumen, acumular=True)
    await _desafio_progress_safe(telegram_id, "sesiones", 1.0, acumular=True)
