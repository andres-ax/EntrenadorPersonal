"""PersonalRecord polimorfico + SesionEntrenamiento extendido (PR3).

Revision ID: 0006_pr_polimorfico
Revises: 0005_seed_deportes
Create Date: 2026-05-17

Cambios:
- PersonalRecord: +tipo_pr, +deporte, +video_url, +spot, +grado, +tiempo_seg,
  +profundidad_m, +watts, +velocidad_kmh, +rondas, +cinturon, +distancia_m, +notas.
  peso_kg cambia de NOT NULL a NULLABLE (truco/grado/tiempo no tienen peso).
- SesionEntrenamiento: +subtipo, +intensidad_1_10, +num_caidas, +sensacion_1_5,
  +spot, +deporte_slug, +trucos_intentados, +trucos_aterrizados, +rounds,
  +co_riders, +foco_sesion.

Defaults backward-compatible: PRs viejos siguen funcionando con tipo_pr=PESO_REPS.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_pr_polimorfico"
down_revision: Union[str, None] = "0005_seed_deportes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PR_NUEVOS = [
    ("tipo_pr", sa.String(20), {"server_default": "peso_reps", "nullable": False}),
    ("deporte", sa.String(48), {"nullable": True}),
    ("video_url", sa.String(300), {"nullable": True}),
    ("spot", sa.String(120), {"nullable": True}),
    ("grado", sa.String(16), {"nullable": True}),
    ("tiempo_seg", sa.Float, {"nullable": True}),
    ("profundidad_m", sa.Float, {"nullable": True}),
    ("watts", sa.Integer, {"nullable": True}),
    ("velocidad_kmh", sa.Float, {"nullable": True}),
    ("rondas", sa.Integer, {"nullable": True}),
    ("cinturon", sa.String(32), {"nullable": True}),
    ("distancia_m", sa.Float, {"nullable": True}),
    ("notas", sa.Text, {"nullable": True}),
]

SESION_NUEVAS = [
    ("subtipo", sa.String(24), {"server_default": "sets", "nullable": False}),
    ("intensidad_1_10", sa.Integer, {"nullable": True}),
    ("num_caidas", sa.Integer, {"server_default": "0"}),
    ("sensacion_1_5", sa.Integer, {"nullable": True}),
    ("spot", sa.String(120), {"nullable": True}),
    ("deporte_slug", sa.String(48), {"nullable": True}),
    ("trucos_intentados", sa.Integer, {"server_default": "0"}),
    ("trucos_aterrizados", sa.Integer, {"server_default": "0"}),
    ("rounds", sa.Integer, {"nullable": True}),
    ("co_riders", sa.String(200), {"nullable": True}),
    ("foco_sesion", sa.String(120), {"nullable": True}),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    pr_cols = {c["name"] for c in inspector.get_columns("personal_records")}
    for name, col_type, kw in PR_NUEVOS:
        if name not in pr_cols:
            op.add_column("personal_records", sa.Column(name, col_type, **kw))
    op.create_index(
        "ix_pr_tipo_pr",
        "personal_records",
        ["tipo_pr"],
        if_not_exists=True if bind.dialect.name == "postgresql" else False,
    ) if "tipo_pr" not in pr_cols else None
    op.create_index(
        "ix_pr_deporte",
        "personal_records",
        ["deporte"],
        if_not_exists=True if bind.dialect.name == "postgresql" else False,
    ) if "deporte" not in pr_cols else None

    try:
        op.alter_column(
            "personal_records",
            "peso_kg",
            existing_type=sa.Float(),
            nullable=True,
        )
    except Exception:
        pass

    sesion_cols = {c["name"] for c in inspector.get_columns("sesiones_entrenamiento")}
    for name, col_type, kw in SESION_NUEVAS:
        if name not in sesion_cols:
            op.add_column("sesiones_entrenamiento", sa.Column(name, col_type, **kw))
    op.create_index(
        "ix_sesion_deporte_slug",
        "sesiones_entrenamiento",
        ["deporte_slug"],
        if_not_exists=True if bind.dialect.name == "postgresql" else False,
    ) if "deporte_slug" not in sesion_cols else None


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    pr_cols = {c["name"] for c in inspector.get_columns("personal_records")}
    sesion_cols = {c["name"] for c in inspector.get_columns("sesiones_entrenamiento")}

    for name, _, _ in reversed(PR_NUEVOS):
        if name in pr_cols:
            op.drop_column("personal_records", name)
    for name, _, _ in reversed(SESION_NUEVAS):
        if name in sesion_cols:
            op.drop_column("sesiones_entrenamiento", name)
    try:
        op.alter_column(
            "personal_records",
            "peso_kg",
            existing_type=sa.Float(),
            nullable=False,
        )
    except Exception:
        pass
