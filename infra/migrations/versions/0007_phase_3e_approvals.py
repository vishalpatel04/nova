"""Phase 3E capability approval requests."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_phase_3e_approvals"
down_revision: str | None = "0006_phase_3c_ux"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("action_summary", sa.String(length=512), nullable=False),
        sa.Column("command_or_payload_preview", sa.Text(), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_user_id", "approval_requests", ["user_id"])
    op.create_index("ix_approval_requests_device_id", "approval_requests", ["device_id"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])
    op.create_index(
        "ix_approval_requests_action_fingerprint",
        "approval_requests",
        ["action_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index("ix_approval_requests_action_fingerprint", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_device_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_user_id", table_name="approval_requests")
    op.drop_table("approval_requests")
