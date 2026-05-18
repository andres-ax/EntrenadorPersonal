"""Quitar constraint UNIQUE de foto_sha256 en pagos_comprobantes.

Revision ID: 0010_drop_unique_foto_sha256
Revises: 0009_sesion_abierta
Create Date: 2026-05-18

Problema: ahora guardamos comprobantes SIEMPRE (incluso si Vision rechaza
la foto). Si el usuario envia la misma foto 2 veces, el INSERT explota
con UniqueViolationError en ix_pagos_comprobantes_foto_sha256.

La deteccion de duplicados ya se hace por logica en
`src/services/deteccion_duplicados.es_duplicado()` (compara sha256, monto,
referencia, etc.). No necesitamos el constraint UNIQUE a nivel DB.

Solucion: DROP el index UNIQUE y recrear como index normal (sin unique).
"""

from alembic import op

revision = "0010_drop_unique_foto_sha256"
down_revision = "0009_sesion_abierta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_pagos_comprobantes_foto_sha256", table_name="pagos_comprobantes")
    op.create_index(
        "ix_pagos_comprobantes_foto_sha256",
        "pagos_comprobantes",
        ["foto_sha256"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pagos_comprobantes_foto_sha256", table_name="pagos_comprobantes")
    op.create_index(
        "ix_pagos_comprobantes_foto_sha256",
        "pagos_comprobantes",
        ["foto_sha256"],
        unique=True,
    )
