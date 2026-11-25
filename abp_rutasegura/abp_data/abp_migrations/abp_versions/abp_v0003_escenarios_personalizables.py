from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("escenario", schema=None) as abp_batch_op:
        abp_batch_op.add_column(
            sa.Column("descripcion", sa.Text(), server_default="", nullable=False)
        )
        abp_batch_op.add_column(
            sa.Column("factor_reaccion", sa.Float(), server_default="1.0", nullable=False)
        )
        abp_batch_op.add_column(
            sa.Column("factor_velocidad", sa.Float(), server_default="1.0", nullable=False)
        )
        abp_batch_op.add_column(
            sa.Column("corridas", sa.Integer(), server_default="1", nullable=False)
        )
    with op.batch_alter_table("simulacion", schema=None) as abp_batch_op:
        abp_batch_op.add_column(sa.Column("estadisticas", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("simulacion", schema=None) as abp_batch_op:
        abp_batch_op.drop_column("estadisticas")
    with op.batch_alter_table("escenario", schema=None) as abp_batch_op:
        abp_batch_op.drop_column("corridas")
        abp_batch_op.drop_column("factor_velocidad")
        abp_batch_op.drop_column("factor_reaccion")
        abp_batch_op.drop_column("descripcion")
