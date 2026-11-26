from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ambiente", schema=None) as abp_batch_op:
        abp_batch_op.add_column(
            sa.Column("salida", sa.String(length=80), server_default="", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("ambiente", schema=None) as abp_batch_op:
        abp_batch_op.drop_column("salida")
