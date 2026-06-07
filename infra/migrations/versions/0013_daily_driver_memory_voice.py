"""Daily driver chat memory and voice preferences."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_daily_driver_memory_voice"
down_revision: str | None = "0012_pending_tool_intent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_memory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value_summary", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="user"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.9"),
        sa.Column("user_editable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "key", name="uq_user_memory_user_key"),
    )
    op.create_index("ix_user_memory_user_id", "user_memory", ["user_id"])
    op.create_index("ix_user_memory_key", "user_memory", ["key"])


def downgrade() -> None:
    op.drop_index("ix_user_memory_key", table_name="user_memory")
    op.drop_index("ix_user_memory_user_id", table_name="user_memory")
    op.drop_table("user_memory")
