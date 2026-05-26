"""Google Play Billing: MetodoPago google_play + columnas en suscripciones + RTDN events.

Revision ID: 0016_google_play_billing
Revises: 0015_phone_auth
Create Date: 2026-05-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_google_play_billing"
down_revision: Union[str, None] = "0015_phone_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE metodopago ADD VALUE IF NOT EXISTS 'google_play'")

    op.add_column(
        "suscripciones",
        sa.Column("google_purchase_token", sa.String(512), nullable=True),
    )
    op.add_column(
        "suscripciones",
        sa.Column("google_order_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "suscripciones",
        sa.Column("google_product_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "suscripciones",
        sa.Column("google_base_plan_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "suscripciones",
        sa.Column("google_linked_purchase_token", sa.String(512), nullable=True),
    )
    op.create_index(
        "ix_suscripciones_google_purchase_token",
        "suscripciones",
        ["google_purchase_token"],
        unique=True,
    )

    op.create_table(
        "google_play_rtdn_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("message_id", sa.String(128), nullable=False),
        sa.Column("notification_type", sa.Integer(), nullable=True),
        sa.Column("purchase_token", sa.String(512), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_google_play_rtdn_events_message_id",
        "google_play_rtdn_events",
        ["message_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_google_play_rtdn_events_message_id", table_name="google_play_rtdn_events")
    op.drop_table("google_play_rtdn_events")
    op.drop_index("ix_suscripciones_google_purchase_token", table_name="suscripciones")
    op.drop_column("suscripciones", "google_linked_purchase_token")
    op.drop_column("suscripciones", "google_base_plan_id")
    op.drop_column("suscripciones", "google_product_id")
    op.drop_column("suscripciones", "google_order_id")
    op.drop_column("suscripciones", "google_purchase_token")
    # Postgres no permite quitar valores de enum sin recrear el tipo; se deja google_play.
