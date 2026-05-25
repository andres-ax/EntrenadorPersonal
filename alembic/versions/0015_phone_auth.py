"""Autenticacion por telefono: columnas telefono y phone_verified_at en usuarios.

Revision ID: 0015_phone_auth
Revises: 0014_desafios_diarios
Create Date: 2026-05-25

El codigo de auth movil (request-otp, verify-otp, completar perfil) consulta
usuarios.telefono; sin esta migracion prod falla con UndefinedColumnError.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_phone_auth"
down_revision: Union[str, None] = "0014_desafios_diarios"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("usuarios")}

    if "telefono" not in cols:
        op.add_column(
            "usuarios",
            sa.Column("telefono", sa.String(length=20), nullable=True),
        )

    if "phone_verified_at" not in cols:
        op.add_column(
            "usuarios",
            sa.Column("phone_verified_at", sa.DateTime(), nullable=True),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("usuarios")}
    if "ix_usuarios_telefono" not in indexes:
        op.create_index(
            "ix_usuarios_telefono",
            "usuarios",
            ["telefono"],
            unique=True,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("usuarios")}
    if "ix_usuarios_telefono" in indexes:
        op.drop_index("ix_usuarios_telefono", table_name="usuarios")

    cols = {c["name"] for c in inspector.get_columns("usuarios")}
    if "phone_verified_at" in cols:
        op.drop_column("usuarios", "phone_verified_at")
    if "telefono" in cols:
        op.drop_column("usuarios", "telefono")
