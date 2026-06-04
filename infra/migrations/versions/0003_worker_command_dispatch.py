"""Worker command dispatch assignments."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_worker_command_dispatch"
down_revision: str | None = "0002_live_nervous_system"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_command_assignments",
        sa.Column("command_id", sa.String(length=128), nullable=False),
        sa.Column("mission_id", sa.String(length=36), nullable=True),
        sa.Column("command_type", sa.String(length=64), nullable=False),
        sa.Column("routing_mode", sa.String(length=32), nullable=False),
        sa.Column("target_device_id", sa.String(length=64), nullable=True),
        sa.Column("target_worker_class", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assigned_device_id", sa.String(length=64), nullable=True),
        sa.Column("stream_key", sa.String(length=255), nullable=True),
        sa.Column("stream_entry_id", sa.String(length=64), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
        sa.PrimaryKeyConstraint("command_id"),
    )
    op.create_index(
        "ix_worker_command_assignments_mission_id",
        "worker_command_assignments",
        ["mission_id"],
    )
    op.create_index(
        "ix_worker_command_assignments_status",
        "worker_command_assignments",
        ["status"],
    )
    op.create_index(
        "ix_worker_command_assignments_target_device_id",
        "worker_command_assignments",
        ["target_device_id"],
    )
    op.create_index(
        "ix_worker_command_assignments_target_worker_class",
        "worker_command_assignments",
        ["target_worker_class"],
    )
    op.create_index(
        "ix_worker_command_assignments_assigned_device_id",
        "worker_command_assignments",
        ["assigned_device_id"],
    )


def downgrade() -> None:
    op.drop_table("worker_command_assignments")
