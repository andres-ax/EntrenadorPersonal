"""Tabla auditoria_turnos para auditoría persistente de turnos y tools.

Revision ID: 0012
Revises: 0011_llm_usage
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_auditoria_turnos"
down_revision = "0011_llm_usage"


def upgrade() -> None:
    op.create_table(
        "auditoria_turnos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column(
            "usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("request_id", sa.String(length=100), nullable=True, index=True),
        sa.Column("prompt_usuario", sa.Text(), nullable=True),
        sa.Column("respuesta_bot", sa.Text(), nullable=True),
        sa.Column("tools_invocadas", sa.JSON(), nullable=True),
        sa.Column("tokens_input", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("costo_estimado_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("duracion_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(),
            server_default=sa.func.now(),
            index=True,
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("auditoria_turnos")
