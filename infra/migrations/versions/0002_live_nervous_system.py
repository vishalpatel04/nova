"""Slice 2A — auth, pairing, events, worker live path."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_live_nervous_system"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("architecture", sa.String(64), nullable=True))
    op.add_column("devices", sa.Column("memory_mb", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("gpu_available", sa.Boolean(), nullable=True))
    op.add_column("devices", sa.Column("privacy_class", sa.String(32), server_default="owner"))
    op.add_column("devices", sa.Column("token_state", sa.String(32), server_default="active"))
    op.add_column("devices", sa.Column("connection_status", sa.String(32), nullable=True))

    op.add_column("timeline_events", sa.Column("sequence_number", sa.Integer(), nullable=True))
    op.add_column("timeline_events", sa.Column("stream_id", sa.String(128), nullable=True))
    op.create_index("ix_timeline_events_sequence", "timeline_events", ["sequence_number"])

    try:
        op.drop_constraint("uq_mission_idempotency", "missions", type_="unique")
    except Exception:
        pass

    op.create_table(
        "device_pairing_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False, unique=True),
        sa.Column("device_type", sa.String(64), nullable=False),
        sa.Column("proposed_device_id", sa.String(64), nullable=True),
        sa.Column("proposed_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), server_default="pending"),
        sa.Column("requires_approval", sa.Boolean(), server_default="true"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "device_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("token_prefix", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("credential_type", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), server_default="active"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_from_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "device_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column(
            "credential_id", sa.String(36), sa.ForeignKey("device_credentials.id"), nullable=False
        ),
        sa.Column("connection_type", sa.String(32), nullable=False),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "token_revocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "credential_id", sa.String(36), sa.ForeignKey("device_credentials.id"), nullable=False
        ),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("revoked_by", sa.String(64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("principal_id", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "principal_id", "scope", "idempotency_key", name="uq_idempotency_scoped"
        ),
    )

    op.create_table(
        "mission_event_sequences",
        sa.Column("mission_id", sa.String(36), sa.ForeignKey("missions.id"), primary_key=True),
        sa.Column("last_sequence", sa.Integer(), server_default="0", nullable=False),
    )

    op.create_table(
        "queued_missions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_id", sa.String(36), sa.ForeignKey("missions.id"), nullable=False, unique=True
        ),
        sa.Column("required_device_types", sa.JSON(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0"),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_by_device_id", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("queued_missions")
    op.drop_table("mission_event_sequences")
    op.drop_table("idempotency_records")
    op.drop_table("token_revocations")
    op.drop_table("device_sessions")
    op.drop_table("device_credentials")
    op.drop_table("device_pairing_codes")
    op.drop_index("ix_timeline_events_sequence", "timeline_events")
    op.drop_column("timeline_events", "stream_id")
    op.drop_column("timeline_events", "sequence_number")
    op.drop_column("devices", "connection_status")
    op.drop_column("devices", "token_state")
    op.drop_column("devices", "privacy_class")
    op.drop_column("devices", "gpu_available")
    op.drop_column("devices", "memory_mb")
    op.drop_column("devices", "architecture")
