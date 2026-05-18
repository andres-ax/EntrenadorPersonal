"""Sesion abierta/cerrada + updated_at para deduplicar entrenos.

Revision ID: 0009_sesion_abierta
Revises: 0008_data_integrity
Create Date: 2026-05-18

Problema detectado en prod:
- Andy (8324604749) mando 3 mensajes describiendo el mismo entreno de
  skate y se crearon 3 filas en `sesiones_entrenamiento` porque
  `guardar_sesion_skill` siempre hace INSERT.

Solucion:
- Columna `cerrada` BOOL DEFAULT TRUE (backfill: las viejas se quedan
  como cerradas para que el flujo nuevo no las altere).
- Columna `updated_at` DATETIME server_default NOW.
- Indice `(usuario_id, fecha, cerrada)` para que la query de "sesion
  abierta del dia" sea rapida.

Logica nueva en repository: cuando hay una sesion del mismo usuario +
fecha + deporte + cerrada=False + updated_at >= NOW-2h, hacemos UPDATE
en vez de INSERT. Asi 3 mensajes del mismo entreno = 1 fila.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0009_sesion_abierta"
down_revision: Union[str, None] = "0008_data_integrity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("sesiones_entrenamiento")}

    if "cerrada" not in cols:
        op.add_column(
            "sesiones_entrenamiento",
            sa.Column(
                "cerrada",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
        )

    if "updated_at" not in cols:
        op.add_column(
            "sesiones_entrenamiento",
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # Indice para buscar sesion abierta del dia rapidamente.
    indexes = {idx["name"] for idx in inspector.get_indexes("sesiones_entrenamiento")}
    if "ix_sesiones_abiertas" not in indexes:
        op.create_index(
            "ix_sesiones_abiertas",
            "sesiones_entrenamiento",
            ["usuario_id", "fecha", "cerrada"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("sesiones_entrenamiento")}
    if "ix_sesiones_abiertas" in indexes:
        op.drop_index("ix_sesiones_abiertas", table_name="sesiones_entrenamiento")

    cols = {c["name"] for c in inspector.get_columns("sesiones_entrenamiento")}
    if "updated_at" in cols:
        op.drop_column("sesiones_entrenamiento", "updated_at")
    if "cerrada" in cols:
        op.drop_column("sesiones_entrenamiento", "cerrada")
