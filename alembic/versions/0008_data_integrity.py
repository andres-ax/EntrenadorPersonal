"""Integridad de datos: eventos_bot.telegram_id + CHECK constraints + limpieza.

Revision ID: 0008_data_integrity
Revises: 0007_recordatorios
Create Date: 2026-05-18

Cambios derivados de la auditoria de datos en prod:

1. `eventos_bot.telegram_id` BIGINT NULL: para mantener trazabilidad de
   eventos despues de que el usuario se borre (hoy quedan huerfanos al
   borrar_datos porque solo guardamos `usuario_id` FK).

2. CHECK constraints defensivos:
   - `metricas_sueno.horas > 0 AND horas <= 16`
   - `metricas_corporales.peso_kg > 20 AND peso_kg < 400`

3. Limpieza de datos corruptos detectados:
   - DELETE FROM metricas_sueno WHERE horas <= 0
     (Andy tenia 2 filas con horas=0.0 porque el LLM llamaba la tool sin
     tener el dato. Ya fue arreglado en src/tools.py.)
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008_data_integrity"
down_revision: Union[str, None] = "0007_recordatorios"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Limpieza preventiva: borrar filas que violarian los CHECK que
    #    agregaremos despues. Idempotente.
    op.execute(
        "DELETE FROM metricas_sueno WHERE horas IS NULL OR horas <= 0 OR horas > 16"
    )
    op.execute(
        "DELETE FROM metricas_corporales "
        "WHERE peso_kg IS NULL OR peso_kg <= 20 OR peso_kg >= 400"
    )

    # 2. Agregar columna eventos_bot.telegram_id (nullable, sin FK porque
    #    el usuario puede haberse borrado).
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("eventos_bot")]
    if "telegram_id" not in cols:
        op.add_column(
            "eventos_bot",
            sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        )
        op.create_index(
            "ix_eventos_bot_telegram_id",
            "eventos_bot",
            ["telegram_id"],
        )
        # Backfill: copia telegram_id de la tabla usuarios cuando el FK
        # todavia apunta a una fila viva.
        op.execute("""UPDATE eventos_bot e
               SET telegram_id = u.telegram_id
               FROM usuarios u
               WHERE e.usuario_id = u.id
                 AND e.telegram_id IS NULL""")

    # 3. CHECK constraints. Usamos nombres explicitos para downgrade limpio.
    # Postgres no permite IF NOT EXISTS en ADD CONSTRAINT; usamos check
    # antes via information_schema.
    def _add_check(table: str, name: str, expr: str) -> None:
        row = bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"),
            {"n": name},
        ).fetchone()
        if row is None:
            op.execute(f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" CHECK ({expr})')

    _add_check(
        "metricas_sueno",
        "ck_metricas_sueno_horas_rango",
        "horas > 0 AND horas <= 16",
    )
    _add_check(
        "metricas_corporales",
        "ck_metricas_corporales_peso_rango",
        "peso_kg > 20 AND peso_kg < 400",
    )


def downgrade() -> None:
    # Drop checks
    op.execute(
        'ALTER TABLE "metricas_corporales" DROP CONSTRAINT IF EXISTS "ck_metricas_corporales_peso_rango"'
    )
    op.execute(
        'ALTER TABLE "metricas_sueno" DROP CONSTRAINT IF EXISTS "ck_metricas_sueno_horas_rango"'
    )

    # Drop telegram_id column
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c["name"] for c in inspector.get_columns("eventos_bot")]
    if "telegram_id" in cols:
        op.drop_index("ix_eventos_bot_telegram_id", table_name="eventos_bot")
        op.drop_column("eventos_bot", "telegram_id")
