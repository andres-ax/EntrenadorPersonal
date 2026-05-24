"""Desafios diarios por cohorte: columnas, opt-in, progreso log."""
from alembic import op
import sqlalchemy as sa

revision = "0014_desafios_diarios"
down_revision = "0013_task_audit"


def upgrade() -> None:
    op.add_column(
        "desafios",
        sa.Column("duracion", sa.String(length=16), server_default="dia", nullable=False),
    )
    op.add_column(
        "desafios",
        sa.Column("metrica", sa.String(length=32), server_default="minutos_entreno", nullable=False),
    )
    op.add_column(
        "desafios",
        sa.Column("meta_valor", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "desafios",
        sa.Column("cohorte_key", sa.String(length=128), nullable=True),
    )
    op.add_column("desafios", sa.Column("reglas_json", sa.JSON(), nullable=True))
    op.add_column(
        "desafios",
        sa.Column("auto_generado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "desafios",
        sa.Column("estado", sa.String(length=16), server_default="activo", nullable=False),
    )
    op.add_column("desafios", sa.Column("premio_json", sa.JSON(), nullable=True))
    op.create_index("ix_desafios_cohorte_key", "desafios", ["cohorte_key"])
    op.create_index(
        "ix_desafios_cohorte_dia_unico",
        "desafios",
        ["cohorte_key", "fecha_inicio"],
        unique=True,
        postgresql_where=sa.text("auto_generado = true AND duracion = 'dia'"),
    )

    op.add_column(
        "usuarios",
        sa.Column(
            "desafios_opt_in",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.add_column(
        "desafios_participantes",
        sa.Column("premio_otorgado", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "desafio_progreso_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "desafio_id",
            sa.Integer(),
            sa.ForeignKey("desafios.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "usuario_id",
            sa.Integer(),
            sa.ForeignKey("usuarios.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("evento", sa.String(length=32), nullable=False),
        sa.Column("delta", sa.Float(), nullable=False, server_default="0"),
        sa.Column("valor_despues", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "creado_en",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("desafio_progreso_log")
    op.drop_column("desafios_participantes", "premio_otorgado")
    op.drop_column("usuarios", "desafios_opt_in")
    op.drop_index("ix_desafios_cohorte_dia_unico", table_name="desafios")
    op.drop_index("ix_desafios_cohorte_key", table_name="desafios")
    op.drop_column("desafios", "premio_json")
    op.drop_column("desafios", "estado")
    op.drop_column("desafios", "auto_generado")
    op.drop_column("desafios", "reglas_json")
    op.drop_column("desafios", "cohorte_key")
    op.drop_column("desafios", "meta_valor")
    op.drop_column("desafios", "metrica")
    op.drop_column("desafios", "duracion")
