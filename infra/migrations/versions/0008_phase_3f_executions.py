"""Phase 3F controlled shell execution records."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_phase_3f_executions"
down_revision: str | None = "0007_phase_3e_approvals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shell_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("command_preview", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stdout_excerpt", sa.Text(), nullable=True),
        sa.Column("stderr_excerpt", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_id", name="uq_shell_executions_approval_id"),
    )
    op.create_index("ix_shell_executions_approval_id", "shell_executions", ["approval_id"])
    op.create_index("ix_shell_executions_user_id", "shell_executions", ["user_id"])
    op.create_index("ix_shell_executions_device_id", "shell_executions", ["device_id"])
    op.create_index("ix_shell_executions_status", "shell_executions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_shell_executions_status", table_name="shell_executions")
    op.drop_index("ix_shell_executions_device_id", table_name="shell_executions")
    op.drop_index("ix_shell_executions_user_id", table_name="shell_executions")
    op.drop_index("ix_shell_executions_approval_id", table_name="shell_executions")
    op.drop_table("shell_executions")
