"""Phase 3C companion inbox and scheduler metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_phase_3c_ux"
down_revision: str | None = "0005_phase_3b_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "companion_inbox_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("source_device_id", sa.String(length=64), nullable=True),
        sa.Column("target_device_id", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("message_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_companion_inbox_items_target_device_id",
        "companion_inbox_items",
        ["target_device_id"],
    )
    op.create_index("ix_companion_inbox_items_user_id", "companion_inbox_items", ["user_id"])
    op.create_index("ix_companion_inbox_items_status", "companion_inbox_items", ["status"])


def downgrade() -> None:
    op.drop_index("ix_companion_inbox_items_status", table_name="companion_inbox_items")
    op.drop_index("ix_companion_inbox_items_user_id", table_name="companion_inbox_items")
    op.drop_index(
        "ix_companion_inbox_items_target_device_id",
        table_name="companion_inbox_items",
    )
    op.drop_table("companion_inbox_items")
