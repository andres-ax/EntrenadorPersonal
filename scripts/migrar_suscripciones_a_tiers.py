"""Migra suscripciones legacy v1 (free/pro) al nuevo sistema de tiers v2.

Comportamiento:
- usuarios.plan_actual = PRO si tiene suscripcion activa pro no expirada.
- Marca metodo_pago de suscripciones legacy como 'telegram_stars'.
- Usuario sin suscripcion -> plan_actual = FREE (default ya seteado por migracion).
- Dry-run por defecto. Pasa --apply para escribir cambios.

Uso:
    python scripts/migrar_suscripciones_a_tiers.py            # dry-run
    python scripts/migrar_suscripciones_a_tiers.py --apply    # aplica
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from src.db.connection import async_session_factory  # noqa: E402
from src.db.models import (  # noqa: E402
    MetodoPago,
    PlanSuscripcion,
    Suscripcion,
    Usuario,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def migrar(apply: bool) -> None:
    cambios = 0
    ahora = datetime.utcnow()
    async with async_session_factory() as session:
        result = await session.execute(select(Usuario))
        usuarios = list(result.scalars().all())
        logger.info("Procesando %s usuarios", len(usuarios))
        for u in usuarios:
            sub_q = await session.execute(
                select(Suscripcion).where(
                    Suscripcion.usuario_id == u.id,
                    Suscripcion.plan == PlanSuscripcion.PRO,
                    Suscripcion.activa == True,  # noqa: E712
                )
            )
            sub_activa = sub_q.scalars().first()
            if sub_activa and (
                sub_activa.expira_en is None or sub_activa.expira_en > ahora
            ):
                if u.plan_actual != PlanSuscripcion.PRO:
                    logger.info(
                        "uid=%s -> PRO (expira=%s)", u.telegram_id, sub_activa.expira_en
                    )
                    cambios += 1
                    if apply:
                        u.plan_actual = PlanSuscripcion.PRO
                        u.plan_expira_en = sub_activa.expira_en
                if sub_activa.metodo_pago is None or sub_activa.metodo_pago == MetodoPago.MANUAL_ADMIN:
                    if apply:
                        sub_activa.metodo_pago = MetodoPago.TELEGRAM_STARS
            else:
                if u.plan_actual not in (PlanSuscripcion.FREE, PlanSuscripcion.LIFETIME):
                    logger.info(
                        "uid=%s -> FREE (sin sub activa)", u.telegram_id
                    )
                    cambios += 1
                    if apply:
                        u.plan_actual = PlanSuscripcion.FREE
                        u.plan_expira_en = None
        if apply:
            await session.commit()
        logger.info("Cambios %s: %s", "aplicados" if apply else "(dry-run)", cambios)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios")
    args = parser.parse_args()
    asyncio.run(migrar(apply=args.apply))


if __name__ == "__main__":
    main()
