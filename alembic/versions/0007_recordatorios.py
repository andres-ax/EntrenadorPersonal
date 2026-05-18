"""Tabla recordatorios para alarmas personalizadas via chat.

Revision ID: 0007_recordatorios
Revises: 0006_pr_polimorfico
Create Date: 2026-05-17

Recordatorios one-shot (fecha_unica) o recurrentes semanales (dias_semana).
Cargados al JobQueue al boot (src/telegram/scheduler.py).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_recordatorios"
down_revision: Union[str, None] = "0006_pr_polimorfico"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())
    if "recordatorios" in existing:
        return

    op.create_table(
        "recordatorios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("mensaje", sa.String(length=500), nullable=False),
        sa.Column("hora", sa.Time(), nullable=False),
        sa.Column(
            "dias_semana",
            sa.String(length=32),
            nullable=False,
            server_default="",
        ),
        sa.Column("fecha_unica", sa.Date(), nullable=True),
        sa.Column(
            "tz",
            sa.String(length=64),
            nullable=False,
            server_default="America/Bogota",
        ),
        sa.Column(
            "activo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
        ),
        sa.Column("ultimo_envio", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_recordatorios_usuario_id",
        "recordatorios",
        ["usuario_id"],
    )
    op.create_index(
        "ix_recordatorios_telegram_id",
        "recordatorios",
        ["telegram_id"],
    )
    op.create_index(
        "ix_recordatorios_activo",
        "recordatorios",
        ["activo"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "recordatorios" not in set(inspector.get_table_names()):
        return
    op.drop_index("ix_recordatorios_activo", table_name="recordatorios")
    op.drop_index("ix_recordatorios_telegram_id", table_name="recordatorios")
    op.drop_index("ix_recordatorios_usuario_id", table_name="recordatorios")
    op.drop_table("recordatorios")
