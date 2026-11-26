from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("simulacion", schema=None) as abp_batch_op:
        abp_batch_op.add_column(
            sa.Column("huella_plano", sa.String(length=64), server_default="", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("simulacion", schema=None) as abp_batch_op:
        abp_batch_op.drop_column("huella_plano")
