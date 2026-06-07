"""Milestone 1 useful local coding agent — project context, patches, tasks."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_milestone_1_useful_agent"
down_revision: str | None = "0008_phase_3f_executions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "active_projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=False),
        sa.Column("project_name", sa.String(length=255), nullable=False),
        sa.Column("current_branch", sa.String(length=255), nullable=True),
        sa.Column("detected_tooling", sa.JSON(), nullable=True),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", name="uq_active_projects_device_id"),
    )
    op.create_index("ix_active_projects_user_id", "active_projects", ["user_id"])
    op.create_index("ix_active_projects_device_id", "active_projects", ["device_id"])

    op.create_table(
        "project_memory",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=False),
        sa.Column("last_validation_command", sa.String(length=512), nullable=True),
        sa.Column("last_validation_result", sa.JSON(), nullable=True),
        sa.Column("last_patch_proposal", sa.JSON(), nullable=True),
        sa.Column("last_task_summary", sa.Text(), nullable=True),
        sa.Column("recent_task_history", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "device_id", "project_root", name="uq_project_memory_scope"),
    )
    op.create_index("ix_project_memory_user_id", "project_memory", ["user_id"])
    op.create_index("ix_project_memory_device_id", "project_memory", ["device_id"])
    op.create_index("ix_project_memory_project_root", "project_memory", ["project_root"])

    op.create_table(
        "patch_executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("action_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=False),
        sa.Column("patch_preview", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("applied_files", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["approval_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_id", name="uq_patch_executions_approval_id"),
    )
    op.create_index("ix_patch_executions_approval_id", "patch_executions", ["approval_id"])
    op.create_index("ix_patch_executions_user_id", "patch_executions", ["user_id"])
    op.create_index("ix_patch_executions_device_id", "patch_executions", ["device_id"])
    op.create_index("ix_patch_executions_status", "patch_executions", ["status"])

    op.create_table(
        "coding_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=False),
        sa.Column("user_request", sa.Text(), nullable=False),
        sa.Column("approval_id", sa.String(length=36), nullable=True),
        sa.Column("patch_execution_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("timeline", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_coding_tasks_user_id", "coding_tasks", ["user_id"])
    op.create_index("ix_coding_tasks_device_id", "coding_tasks", ["device_id"])
    op.create_index("ix_coding_tasks_stage", "coding_tasks", ["stage"])
    op.create_index("ix_coding_tasks_approval_id", "coding_tasks", ["approval_id"])


def downgrade() -> None:
    op.drop_index("ix_coding_tasks_approval_id", table_name="coding_tasks")
    op.drop_index("ix_coding_tasks_stage", table_name="coding_tasks")
    op.drop_index("ix_coding_tasks_device_id", table_name="coding_tasks")
    op.drop_index("ix_coding_tasks_user_id", table_name="coding_tasks")
    op.drop_table("coding_tasks")

    op.drop_index("ix_patch_executions_status", table_name="patch_executions")
    op.drop_index("ix_patch_executions_device_id", table_name="patch_executions")
    op.drop_index("ix_patch_executions_user_id", table_name="patch_executions")
    op.drop_index("ix_patch_executions_approval_id", table_name="patch_executions")
    op.drop_table("patch_executions")

    op.drop_index("ix_project_memory_project_root", table_name="project_memory")
    op.drop_index("ix_project_memory_device_id", table_name="project_memory")
    op.drop_index("ix_project_memory_user_id", table_name="project_memory")
    op.drop_table("project_memory")

    op.drop_index("ix_active_projects_device_id", table_name="active_projects")
    op.drop_index("ix_active_projects_user_id", table_name="active_projects")
    op.drop_table("active_projects")
