"""Device push tokens para FCM chat.

Revision ID: 0018_chat_realtime_push
Revises: 0017_conversaciones_chat
Create Date: 2026-05-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018_chat_realtime_push"
down_revision: Union[str, None] = "0017_conversaciones_chat"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "device_push_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fcm_token", sa.String(512), nullable=False, unique=True),
        sa.Column("platform", sa.String(16), nullable=False, server_default="android"),
        sa.Column("creado_en", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_device_push_tokens_usuario_id", "device_push_tokens", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_device_push_tokens_usuario_id", table_name="device_push_tokens")
    op.drop_table("device_push_tokens")
