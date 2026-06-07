"""Pending tool intent memory for multi-turn safe tool workflows."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_pending_tool_intent"
down_revision: str | None = "0011_agent_orchestration"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pending_tool_intents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("intent_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pending_tool_intents_session_id", "pending_tool_intents", ["session_id"])
    op.create_index("ix_pending_tool_intents_user_id", "pending_tool_intents", ["user_id"])
    op.create_index("ix_pending_tool_intents_device_id", "pending_tool_intents", ["device_id"])
    op.create_index("ix_pending_tool_intents_intent_type", "pending_tool_intents", ["intent_type"])
    op.create_index("ix_pending_tool_intents_status", "pending_tool_intents", ["status"])


def downgrade() -> None:
    op.drop_index("ix_pending_tool_intents_status", table_name="pending_tool_intents")
    op.drop_index("ix_pending_tool_intents_intent_type", table_name="pending_tool_intents")
    op.drop_index("ix_pending_tool_intents_device_id", table_name="pending_tool_intents")
    op.drop_index("ix_pending_tool_intents_user_id", table_name="pending_tool_intents")
    op.drop_index("ix_pending_tool_intents_session_id", table_name="pending_tool_intents")
    op.drop_table("pending_tool_intents")
