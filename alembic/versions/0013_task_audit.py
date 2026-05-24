"""Revision 0013: task_audit_log, dedup recordatorios, peso_estimado."""
from alembic import op
import sqlalchemy as sa

revision = "0013_task_audit"
down_revision = "0012_auditoria_turnos"


def upgrade() -> None:
    op.create_table(
        "task_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("task_type", sa.String(length=32), nullable=False, index=True),
        sa.Column("action", sa.String(length=32), nullable=False, index=True),
        sa.Column("payload_snapshot", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "creado_en",
            sa.DateTime(),
            server_default=sa.func.now(),
            index=True,
            nullable=False,
        ),
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "peso_estimado",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    # Desactivar duplicados existentes (conservar el id menor) ANTES del índice único
    op.execute(
        """
        UPDATE recordatorios r
        SET activo = false
        FROM (
            SELECT usuario_id, hora, mensaje, MIN(id) AS keep_id
            FROM recordatorios
            WHERE activo = true
            GROUP BY usuario_id, hora, mensaje
            HAVING COUNT(*) > 1
        ) d
        WHERE r.usuario_id = d.usuario_id
          AND r.hora = d.hora
          AND r.mensaje = d.mensaje
          AND r.activo = true
          AND r.id <> d.keep_id
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_recordatorios_activos_dedup
        ON recordatorios (usuario_id, hora, mensaje)
        WHERE activo = true
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_recordatorios_activos_dedup")
    op.drop_column("usuarios", "peso_estimado")
    op.drop_table("task_audit_log")
