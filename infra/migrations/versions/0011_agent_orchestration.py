"""Milestone 3 agent orchestration — plans, steps, project decisions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_agent_orchestration"
down_revision: str | None = "0010_background_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("provider_lane", sa.String(length=32), nullable=False, server_default="local"),
        sa.Column("max_steps", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_plans_user_id", "agent_plans", ["user_id"])
    op.create_index("ix_agent_plans_device_id", "agent_plans", ["device_id"])
    op.create_index("ix_agent_plans_status", "agent_plans", ["status"])

    op.create_table(
        "agent_plan_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("agent_role", sa.String(length=32), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["agent_plans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_plan_steps_plan_id", "agent_plan_steps", ["plan_id"])
    op.create_index("ix_agent_plan_steps_status", "agent_plan_steps", ["status"])

    op.create_table(
        "project_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_plan_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_decisions_user_id", "project_decisions", ["user_id"])
    op.create_index("ix_project_decisions_project_root", "project_decisions", ["project_root"])
    op.create_index("ix_project_decisions_source_plan_id", "project_decisions", ["source_plan_id"])


def downgrade() -> None:
    op.drop_index("ix_project_decisions_source_plan_id", table_name="project_decisions")
    op.drop_index("ix_project_decisions_project_root", table_name="project_decisions")
    op.drop_index("ix_project_decisions_user_id", table_name="project_decisions")
    op.drop_table("project_decisions")
    op.drop_index("ix_agent_plan_steps_status", table_name="agent_plan_steps")
    op.drop_index("ix_agent_plan_steps_plan_id", table_name="agent_plan_steps")
    op.drop_table("agent_plan_steps")
    op.drop_index("ix_agent_plans_status", table_name="agent_plans")
    op.drop_index("ix_agent_plans_device_id", table_name="agent_plans")
    op.drop_index("ix_agent_plans_user_id", table_name="agent_plans")
    op.drop_table("agent_plans")
