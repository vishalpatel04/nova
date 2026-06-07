"""Milestone 2 background agent — scheduled tasks, runs, notifications."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_milestone_2_background_agent"
down_revision: str | None = "0009_milestone_1_useful_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "background_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=True),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("schedule_kind", sa.String(length=32), nullable=False),
        sa.Column("schedule_expression", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_result_summary", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_background_tasks_user_id", "background_tasks", ["user_id"])
    op.create_index("ix_background_tasks_device_id", "background_tasks", ["device_id"])
    op.create_index("ix_background_tasks_task_type", "background_tasks", ["task_type"])
    op.create_index("ix_background_tasks_status", "background_tasks", ["status"])
    op.create_index("ix_background_tasks_next_run_at", "background_tasks", ["next_run_at"])

    op.create_table(
        "background_task_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("audit_metadata", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["task_id"], ["background_tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_background_task_runs_task_id", "background_task_runs", ["task_id"])
    op.create_index("ix_background_task_runs_user_id", "background_task_runs", ["user_id"])
    op.create_index("ix_background_task_runs_device_id", "background_task_runs", ["device_id"])
    op.create_index("ix_background_task_runs_status", "background_task_runs", ["status"])

    op.create_table(
        "notification_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("notification_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notification_items_user_id", "notification_items", ["user_id"])
    op.create_index("ix_notification_items_device_id", "notification_items", ["device_id"])
    op.create_index(
        "ix_notification_items_notification_type", "notification_items", ["notification_type"]
    )
    op.create_index("ix_notification_items_task_id", "notification_items", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_items_task_id", table_name="notification_items")
    op.drop_index("ix_notification_items_notification_type", table_name="notification_items")
    op.drop_index("ix_notification_items_device_id", table_name="notification_items")
    op.drop_index("ix_notification_items_user_id", table_name="notification_items")
    op.drop_table("notification_items")

    op.drop_index("ix_background_task_runs_status", table_name="background_task_runs")
    op.drop_index("ix_background_task_runs_device_id", table_name="background_task_runs")
    op.drop_index("ix_background_task_runs_user_id", table_name="background_task_runs")
    op.drop_index("ix_background_task_runs_task_id", table_name="background_task_runs")
    op.drop_table("background_task_runs")

    op.drop_index("ix_background_tasks_next_run_at", table_name="background_tasks")
    op.drop_index("ix_background_tasks_status", table_name="background_tasks")
    op.drop_index("ix_background_tasks_task_type", table_name="background_tasks")
    op.drop_index("ix_background_tasks_device_id", table_name="background_tasks")
    op.drop_index("ix_background_tasks_user_id", table_name="background_tasks")
    op.drop_table("background_tasks")
