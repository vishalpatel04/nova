"""Initial NOVA schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "agents",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("colour_token", sa.String(64), nullable=True),
        sa.Column("icon_token", sa.String(64), nullable=True),
        sa.Column("voice_profile_id", sa.String(64), nullable=True),
        sa.Column("model_tier", sa.String(32), nullable=True),
        sa.Column("status", sa.String(32), server_default="active"),
        sa.Column("parent_agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("allowed_tool_categories", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "devices",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("device_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="registered"),
        sa.Column("hostname", sa.String(255), nullable=True),
        sa.Column("os_version", sa.String(64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )

    op.create_table(
        "device_capabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False, index=True
        ),
        sa.Column("capability", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true"),
        sa.Column("version", sa.String(64), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("device_id", "capability", name="uq_device_capability"),
    )

    op.create_table(
        "device_heartbeats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False, index=True
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "missions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("mission_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending", index=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("assigned_agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_mission_idempotency"),
    )

    op.create_table(
        "mission_steps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False, index=True
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=True),
        sa.Column("input_payload", sa.JSON(), nullable=True),
        sa.Column("output_payload", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=True, index=True
        ),
        sa.Column(
            "agent_id", sa.String(64), sa.ForeignKey("agents.id"), nullable=False, index=True
        ),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence_badge", sa.String(32), server_default="inferred"),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "timeline_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=True, index=True
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False, index=True
        ),
        sa.Column("step_id", sa.String(36), sa.ForeignKey("mission_steps.id"), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requested_by_agent_id", sa.String(64), nullable=True),
        sa.Column("reviewer_agent_id", sa.String(64), server_default="neptune"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False, index=True
        ),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("uri", sa.String(1024), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "model_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=True, index=True
        ),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("model_tier", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0"),
        sa.Column("output_tokens", sa.Integer(), server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("model_usage")
    op.drop_table("audit_events")
    op.drop_table("artifacts")
    op.drop_table("approvals")
    op.drop_table("timeline_events")
    op.drop_table("agent_messages")
    op.drop_table("mission_steps")
    op.drop_table("missions")
    op.drop_table("device_heartbeats")
    op.drop_table("device_capabilities")
    op.drop_table("devices")
    op.drop_table("agents")
    op.drop_table("users")
