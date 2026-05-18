"""Tabla llm_usage para tracking de costos API OpenAI.

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"


def upgrade() -> None:
    op.create_table(
        "llm_usage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "usuario_id",
            sa.Integer,
            sa.ForeignKey("usuarios.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("telegram_id", sa.BigInteger, nullable=True, index=True),
        sa.Column("servicio", sa.String(32), nullable=False, index=True),
        sa.Column("modelo", sa.String(64), nullable=False),
        sa.Column("input_tokens", sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("costo_estimado_usd", sa.Float, default=0.0),
        sa.Column("rounds", sa.Integer, default=1),
        sa.Column(
            "creado_en",
            sa.DateTime,
            server_default=sa.func.now(),
            index=True,
        ),
    )
    op.create_index(
        "ix_llm_usage_creado_servicio",
        "llm_usage",
        ["creado_en", "servicio"],
    )


def downgrade() -> None:
    op.drop_index("ix_llm_usage_creado_servicio", table_name="llm_usage")
    op.drop_table("llm_usage")
