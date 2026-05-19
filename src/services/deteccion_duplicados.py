"""Deteccion de comprobantes de pago duplicados.

Dos modos:
1. Duplicado total: sha256 exacto -> es la misma imagen subida antes.
2. Duplicado semantico: monto + fecha + referencia + hora cercana (+/-5min)
   -> probablemente el mismo pago reutilizado con foto diferente.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import and_, select

from src.db.connection import async_session_factory
from src.db.models import PagoComprobante

logger = logging.getLogger(__name__)


async def es_duplicado(
    foto_sha256: str,
    monto_cop: int,
    fecha_pago: Optional[datetime],
    referencia: str,
    cuenta_origen: str = "",
    excluir_id: Optional[int] = None,
) -> dict:
    """Devuelve info sobre si el comprobante es duplicado de otro previo.

    Returns:
        {
            "es_duplicado": bool,
            "razon": "sha_exacto" | "semantico" | "no",
            "comprobantes_similares": [ids],
        }

    """
    async with async_session_factory() as session:
        if foto_sha256:
            q = select(PagoComprobante).where(
                PagoComprobante.foto_sha256 == foto_sha256
            )
            if excluir_id is not None:
                q = q.where(PagoComprobante.id != excluir_id)
            result = await session.execute(q)
            existente = result.scalars().first()
            if existente is not None:
                return {
                    "es_duplicado": True,
                    "razon": "sha_exacto",
                    "comprobantes_similares": [existente.id],
                }

        if monto_cop <= 0 or fecha_pago is None or not referencia:
            return {
                "es_duplicado": False,
                "razon": "no",
                "comprobantes_similares": [],
            }

        ventana_inicio = fecha_pago - timedelta(minutes=5)
        ventana_fin = fecha_pago + timedelta(minutes=5)

        condiciones = [
            PagoComprobante.monto_cop == monto_cop,
            PagoComprobante.referencia == referencia,
            PagoComprobante.fecha_pago.is_not(None),
            PagoComprobante.fecha_pago >= ventana_inicio,
            PagoComprobante.fecha_pago <= ventana_fin,
        ]
        q = select(PagoComprobante).where(and_(*condiciones))
        if excluir_id is not None:
            q = q.where(PagoComprobante.id != excluir_id)
        result = await session.execute(q)
        similares = list(result.scalars().all())
        if similares:
            return {
                "es_duplicado": True,
                "razon": "semantico",
                "comprobantes_similares": [s.id for s in similares],
            }

        if cuenta_origen and len(cuenta_origen) >= 4:
            q_cuenta = select(PagoComprobante).where(
                and_(
                    PagoComprobante.monto_cop == monto_cop,
                    PagoComprobante.cuenta_origen == cuenta_origen,
                    PagoComprobante.fecha_pago.is_not(None),
                    PagoComprobante.fecha_pago >= ventana_inicio,
                    PagoComprobante.fecha_pago <= ventana_fin,
                )
            )
            if excluir_id is not None:
                q_cuenta = q_cuenta.where(PagoComprobante.id != excluir_id)
            result2 = await session.execute(q_cuenta)
            similares2 = list(result2.scalars().all())
            if similares2:
                return {
                    "es_duplicado": True,
                    "razon": "semantico",
                    "comprobantes_similares": [s.id for s in similares2],
                }

        return {
            "es_duplicado": False,
            "razon": "no",
            "comprobantes_similares": [],
        }
