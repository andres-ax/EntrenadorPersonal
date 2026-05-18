"""Schema v2: tiers (Free/Starter/Pro/Elite/Lifetime) + pagos por comprobante + admin.

Revision ID: 0003_tiers_pagos
Revises: 0001_initial_v1
Create Date: 2026-05-17

Cambios:
- Extiende enum PlanSuscripcion con STARTER, ELITE, LIFETIME.
- Anade columnas a usuarios (plan_actual, plan_expira_en, referido_por,
  codigo_referido, email, email_verified_at, auth_method).
- Anade columnas a suscripciones (metodo_pago, monto_cop, comprobante_id,
  referido_aplicado).
- Crea tablas: plan_definicion, pagos_comprobantes, usuarios_bloqueados, admins.
- Seed inicial de plan_definicion con los 4 tiers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from src.db.models import (
    Admin,
    PagoComprobante,
    PlanDefinicion,
    Usuario,
    UsuarioBloqueado,
)

revision: str = "0003_tiers_pagos"
down_revision: Union[str, None] = "0001_initial_v1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("ALTER TYPE plansuscripcion ADD VALUE IF NOT EXISTS 'starter'")
        op.execute("ALTER TYPE plansuscripcion ADD VALUE IF NOT EXISTS 'elite'")
        op.execute("ALTER TYPE plansuscripcion ADD VALUE IF NOT EXISTS 'lifetime'")

    with op.batch_alter_table("usuarios") as batch:
        batch.add_column(
            sa.Column(
                "plan_actual",
                sa.Enum(
                    "free",
                    "starter",
                    "pro",
                    "elite",
                    "lifetime",
                    name="plansuscripcion",
                    create_type=False,
                ),
                server_default="free",
                nullable=False,
            )
        )
        batch.add_column(sa.Column("plan_expira_en", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("referido_por", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("codigo_referido", sa.String(32), nullable=True))
        batch.add_column(sa.Column("email", sa.String(180), nullable=True))
        batch.add_column(sa.Column("email_verified_at", sa.DateTime(), nullable=True))
        batch.add_column(
            sa.Column(
                "auth_method",
                sa.String(16),
                server_default="telegram",
                nullable=False,
            )
        )

    op.create_index(
        "ix_usuarios_codigo_referido",
        "usuarios",
        ["codigo_referido"],
        unique=True,
    )
    op.create_index(
        "ix_usuarios_email",
        "usuarios",
        ["email"],
        unique=True,
    )
    op.create_index("ix_usuarios_plan_actual", "usuarios", ["plan_actual"])
    op.create_index("ix_usuarios_referido_por", "usuarios", ["referido_por"])

    Admin.__table__.create(bind, checkfirst=True)
    PlanDefinicion.__table__.create(bind, checkfirst=True)
    PagoComprobante.__table__.create(bind, checkfirst=True)
    UsuarioBloqueado.__table__.create(bind, checkfirst=True)

    op.create_index(
        "ix_pagos_comprobantes_busqueda",
        "pagos_comprobantes",
        ["monto_cop", "fecha_pago", "referencia"],
    )

    with op.batch_alter_table("suscripciones") as batch:
        batch.add_column(
            sa.Column(
                "metodo_pago",
                sa.Enum(
                    "bre_b",
                    "nequi",
                    "daviplata",
                    "bancolombia",
                    "manual_admin",
                    "telegram_stars",
                    "otro",
                    name="metodopago",
                ),
                server_default="manual_admin",
                nullable=False,
            )
        )
        batch.add_column(sa.Column("monto_cop", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column(
                "comprobante_id",
                sa.Integer(),
                sa.ForeignKey("pagos_comprobantes.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "referido_aplicado",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            )
        )

    op.execute(
        """
        INSERT INTO plan_definicion (plan, precio_cop_mensual, precio_cop_anual, features, activo)
        VALUES
        ('free', 0, 0, '{"realtime_min_mes": 0, "fotos_dia": 3, "wearables_max": 0, "voz_tts": false, "plan_generator": false, "pdf_mensual": false, "charts_avanzados": false, "miniapp": true, "export_csv_dias": 30}', true),
        ('starter', 5000, 48000, '{"realtime_min_mes": 5, "fotos_dia": -1, "wearables_max": 1, "voz_tts": false, "plan_generator": false, "pdf_mensual": true, "charts_avanzados": true, "miniapp": true, "export_csv_dias": 90}', true),
        ('pro', 14990, 144000, '{"realtime_min_mes": 30, "fotos_dia": -1, "wearables_max": 1, "voz_tts": true, "plan_generator": true, "pdf_mensual": true, "charts_avanzados": true, "miniapp": true, "export_csv_dias": -1, "stickers_exclusivos": true}', true),
        ('elite', 39990, 384000, '{"realtime_min_mes": 120, "fotos_dia": -1, "wearables_max": -1, "voz_tts": true, "plan_generator": true, "pdf_mensual": true, "pdf_ilimitado": true, "charts_avanzados": true, "miniapp": true, "export_csv_dias": -1, "stickers_exclusivos": true, "beta_features": true, "priority_support": true, "kudos_x3": true}', true),
        ('lifetime', 399000, 0, '{"realtime_min_mes": 120, "fotos_dia": -1, "wearables_max": -1, "voz_tts": true, "plan_generator": true, "pdf_mensual": true, "pdf_ilimitado": true, "charts_avanzados": true, "miniapp": true, "export_csv_dias": -1, "stickers_exclusivos": true, "beta_features": true, "priority_support": true, "kudos_x3": true, "lifetime": true}', true)
        ON CONFLICT (plan) DO NOTHING
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("suscripciones") as batch:
        batch.drop_column("referido_aplicado")
        batch.drop_column("comprobante_id")
        batch.drop_column("monto_cop")
        batch.drop_column("metodo_pago")

    op.drop_table("usuarios_bloqueados")
    op.drop_table("pagos_comprobantes")
    op.drop_table("plan_definicion")
    op.drop_table("admins")

    op.drop_index("ix_usuarios_referido_por", table_name="usuarios")
    op.drop_index("ix_usuarios_plan_actual", table_name="usuarios")
    op.drop_index("ix_usuarios_email", table_name="usuarios")
    op.drop_index("ix_usuarios_codigo_referido", table_name="usuarios")

    with op.batch_alter_table("usuarios") as batch:
        batch.drop_column("auth_method")
        batch.drop_column("email_verified_at")
        batch.drop_column("email")
        batch.drop_column("codigo_referido")
        batch.drop_column("referido_por")
        batch.drop_column("plan_expira_en")
        batch.drop_column("plan_actual")
