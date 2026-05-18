"""Schema v2: wearables, planes_semanales, consumo_agua, comunidad, realtime, magic_links, deportes_catalogo.

Revision ID: 0004_wearables_comunidad
Revises: 0003_tiers_pagos
Create Date: 2026-05-17
"""
from typing import Sequence, Union

from alembic import op

from src.db.models import (
    ConsumoAgua,
    DatosWearableRaw,
    DeporteCatalogo,
    Desafio,
    DesafioParticipante,
    IntegracionWearable,
    Kudos,
    MagicLink,
    PlanSemanal,
    RealtimeSesion,
)

revision: str = "0004_wearables_comunidad"
down_revision: Union[str, None] = "0003_tiers_pagos"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    IntegracionWearable.__table__.create(bind, checkfirst=True)
    DatosWearableRaw.__table__.create(bind, checkfirst=True)
    PlanSemanal.__table__.create(bind, checkfirst=True)
    ConsumoAgua.__table__.create(bind, checkfirst=True)
    Desafio.__table__.create(bind, checkfirst=True)
    DesafioParticipante.__table__.create(bind, checkfirst=True)
    Kudos.__table__.create(bind, checkfirst=True)
    MagicLink.__table__.create(bind, checkfirst=True)
    DeporteCatalogo.__table__.create(bind, checkfirst=True)
    RealtimeSesion.__table__.create(bind, checkfirst=True)


def downgrade() -> None:
    op.drop_table("realtime_sesiones")
    op.drop_table("deportes_catalogo")
    op.drop_table("magic_links")
    op.drop_table("kudos")
    op.drop_table("desafios_participantes")
    op.drop_table("desafios")
    op.drop_table("consumo_agua")
    op.drop_table("planes_semanales")
    op.drop_table("datos_wearables_raw")
    op.drop_table("integraciones_wearables")
