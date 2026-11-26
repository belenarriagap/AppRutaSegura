from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

abp__TEXT_COLUMNS = (
    ("distrito", 120),
    ("provincia", 120),
    ("departamento", 120),
    ("responsable", 200),
    ("cargo_responsable", 200),
    ("telefono", 60),
    ("correo", 200),
    ("horario", 200),
)


def upgrade() -> None:
    with op.batch_alter_table("proyecto", schema=None) as abp_batch_op:
        for abp_name, abp_length in abp__TEXT_COLUMNS:
            abp_batch_op.add_column(
                sa.Column(abp_name, sa.String(length=abp_length), server_default="", nullable=False)
            )
        abp_batch_op.add_column(sa.Column("notas", sa.Text(), server_default="", nullable=False))
        abp_batch_op.add_column(sa.Column("logo", sa.Text(), nullable=True))
    op.create_table(
        "verificacion_regla",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("regla_id", sa.String(length=80), nullable=False, unique=True),
        sa.Column("valor", sa.Float(), nullable=True),
        sa.Column("norma", sa.String(length=120), nullable=False),
        sa.Column("articulo", sa.String(length=120), nullable=False),
        sa.Column("fuente", sa.Text(), nullable=False),
        sa.Column("verificado", sa.Boolean(), nullable=False),
        sa.Column("verificado_por", sa.String(length=200), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("verificacion_regla")
    with op.batch_alter_table("proyecto", schema=None) as abp_batch_op:
        abp_batch_op.drop_column("logo")
        abp_batch_op.drop_column("notas")
        for abp_name, _ in reversed(abp__TEXT_COLUMNS):
            abp_batch_op.drop_column(abp_name)
