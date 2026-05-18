"""Procesado de datos_wearables_raw -> tablas nativas (SesionEntrenamiento, MetricaSueno, etc).

Tras procesar entrenos, cancela escalation del dia (auto-cancel del coach).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select

from src.db.connection import async_session_factory
from src.db.models import (
    DatosWearableRaw,
    IntegracionWearable,
    MetricaSueno,
    SesionEntrenamiento,
    TipoEjercicio,
    Usuario,
)

logger = logging.getLogger(__name__)


def _tipo_ejercicio(payload: dict) -> TipoEjercicio:
    sport = (payload.get("sport_type") or payload.get("type") or "").lower()
    if any(s in sport for s in ["run", "ride", "swim", "row", "elliptical", "walk"]):
        return TipoEjercicio.CARDIO
    if "yoga" in sport or "mobility" in sport or "stretch" in sport:
        return TipoEjercicio.MOVILIDAD
    if any(s in sport for s in ["weight", "strength", "crossfit"]):
        return TipoEjercicio.FUERZA
    return TipoEjercicio.DEPORTE


async def procesar_datos_wearable_raw(ctx) -> int:
    """Convierte datos_wearables_raw sin procesar a tablas nativas."""
    procesados = 0
    async with async_session_factory() as session:
        result = await session.execute(
            select(DatosWearableRaw).where(
                DatosWearableRaw.procesado == False  # noqa: E712
            ).limit(200)
        )
        raws = list(result.scalars().all())

        for raw in raws:
            integ_q = await session.execute(
                select(IntegracionWearable).where(
                    IntegracionWearable.id == raw.integracion_id
                )
            )
            integ = integ_q.scalar_one_or_none()
            if integ is None:
                raw.procesado = True
                continue
            user_q = await session.execute(
                select(Usuario).where(Usuario.id == integ.usuario_id)
            )
            user = user_q.scalar_one_or_none()
            if user is None:
                raw.procesado = True
                continue

            try:
                if raw.tipo == "workout":
                    duracion_min = _extraer_duracion_min(raw.payload)
                    sesion = SesionEntrenamiento(
                        usuario_id=user.id,
                        fecha=raw.fecha,
                        tipo=_tipo_ejercicio(raw.payload),
                        duracion_min=duracion_min,
                        notas=f"Importado de {integ.proveedor}",
                    )
                    session.add(sesion)
                elif raw.tipo == "sleep":
                    horas = _extraer_horas_sueno(raw.payload)
                    if horas > 0:
                        sueno = MetricaSueno(
                            usuario_id=user.id,
                            fecha=raw.fecha,
                            horas=horas,
                            calidad=_calidad_sueno(raw.payload),
                            notas=f"Importado de {integ.proveedor}",
                        )
                        session.add(sueno)
                raw.procesado = True
                raw.procesado_en = datetime.utcnow()
                procesados += 1
            except Exception:
                logger.exception("Error procesando raw=%s", raw.id)
        await session.commit()
    logger.info("Procesados %s datos raw de wearables", procesados)
    return procesados


def _extraer_duracion_min(payload: dict) -> int:
    if "elapsed_time" in payload:
        return int(payload["elapsed_time"]) // 60
    if "moving_time" in payload:
        return int(payload["moving_time"]) // 60
    if "score" in payload and "duration_seconds" in payload.get("score", {}):
        return int(payload["score"]["duration_seconds"]) // 60
    return 0


def _extraer_horas_sueno(payload: dict) -> float:
    if "score" in payload and "stage_summary" in payload["score"]:
        ss = payload["score"]["stage_summary"]
        total_ms = ss.get("total_in_bed_time_milli") or 0
        if total_ms:
            return total_ms / 1000 / 3600
    return 0.0


def _calidad_sueno(payload: dict) -> int:
    if "score" in payload and "sleep_performance_percentage" in payload["score"]:
        pct = payload["score"]["sleep_performance_percentage"]
        if pct >= 90:
            return 5
        if pct >= 75:
            return 4
        if pct >= 60:
            return 3
        if pct >= 40:
            return 2
        return 1
    return 3
