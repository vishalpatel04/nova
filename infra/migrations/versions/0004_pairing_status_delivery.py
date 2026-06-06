"""Pairing status polling and one-time token delivery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_pairing_status_delivery"
down_revision: str | None = "0003_worker_command_dispatch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "device_pairing_codes",
        sa.Column("delivery_consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "device_pairing_codes",
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("device_pairing_codes", "rejected_at")
    op.drop_column("device_pairing_codes", "delivery_consumed_at")
