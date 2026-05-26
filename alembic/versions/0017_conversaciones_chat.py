"""Conversaciones multicanal + mensajes_chat + auditoria canal.

Revision ID: 0017_conversaciones_chat
Revises: 0016_google_play_billing
Create Date: 2026-05-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_conversaciones_chat"
down_revision: Union[str, None] = "0016_google_play_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo", sa.String(120), nullable=False, server_default="Coach"),
        sa.Column("canal_creador", sa.String(16), nullable=False, server_default="telegram"),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("resumen_handoff", sa.Text(), nullable=True),
        sa.Column("ultimo_mensaje_en", sa.DateTime(), nullable=True),
        sa.Column("es_principal", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_conversaciones_usuario_id", "conversaciones", ["usuario_id"])
    op.create_index(
        "ix_conversaciones_usuario_ultimo",
        "conversaciones",
        ["usuario_id", "ultimo_mensaje_en"],
    )

    op.create_table(
        "mensajes_chat",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "conversacion_id",
            sa.Integer(),
            sa.ForeignKey("conversaciones.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("rol", sa.String(16), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("canal_origen", sa.String(16), nullable=False, server_default="telegram"),
        sa.Column(
            "es_desde_telegram",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_mensajes_chat_conversacion_id", "mensajes_chat", ["conversacion_id"])
    op.create_index("ix_mensajes_chat_creado_en", "mensajes_chat", ["creado_en"])

    op.add_column(
        "auditoria_turnos",
        sa.Column(
            "conversacion_id",
            sa.Integer(),
            sa.ForeignKey("conversaciones.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "auditoria_turnos",
        sa.Column("canal", sa.String(16), nullable=False, server_default="telegram"),
    )
    op.create_index(
        "ix_auditoria_turnos_conversacion_id",
        "auditoria_turnos",
        ["conversacion_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_auditoria_turnos_conversacion_id", table_name="auditoria_turnos")
    op.drop_column("auditoria_turnos", "canal")
    op.drop_column("auditoria_turnos", "conversacion_id")
    op.drop_index("ix_mensajes_chat_creado_en", table_name="mensajes_chat")
    op.drop_index("ix_mensajes_chat_conversacion_id", table_name="mensajes_chat")
    op.drop_table("mensajes_chat")
    op.drop_index("ix_conversaciones_usuario_ultimo", table_name="conversaciones")
    op.drop_index("ix_conversaciones_usuario_id", table_name="conversaciones")
    op.drop_table("conversaciones")
