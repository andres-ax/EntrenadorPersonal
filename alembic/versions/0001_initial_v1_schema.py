"""Schema inicial v1: tablas base + extensiones coach molesto.

Revision ID: 0001_initial_v1
Revises:
Create Date: 2026-05-17

Crea el schema completo de EntrenadorAX v1 incluyendo:
- Tablas core: usuarios, sesiones_entrenamiento, ejercicios_realizados,
  comidas, personal_records, metricas_sueno, metricas_corporales.
- Tablas coach molesto: compromisos, escalacion_state, streaks,
  checkins_nocturnos, eventos_bot, crisis_log, feedback_comida, suscripciones.

Para usuarios con DB pre-existente (solo tablas core de la version anterior),
ejecutar primero:
  alembic stamp head    # asume el estado actual
y luego aplicar futuras migraciones normalmente.

Para usuarios nuevos:
  alembic upgrade head  # crea todo desde cero
"""

from typing import Sequence, Union

from alembic import op
from src.db.models import Base

revision: str = "0001_initial_v1"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
