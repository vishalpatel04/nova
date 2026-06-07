"""Local memory kernel migration — pgvector + memory tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_local_memory_kernel"
down_revision: str | None = "0013_daily_driver_memory_voice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "memory_user_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("access_profile", sa.String(length=32), nullable=False, server_default="minimal"),
        sa.Column("override_performance_exclusions", sa.Boolean(), server_default=sa.false()),
        sa.Column("indexing_paused", sa.Boolean(), server_default=sa.false()),
        sa.Column("custom_include_json", sa.JSON(), nullable=True),
        sa.Column("custom_exclude_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_memory_user_settings_user_id"),
    )
    op.create_index("ix_memory_user_settings_user_id", "memory_user_settings", ["user_id"])

    op.create_table(
        "memory_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("root_path", sa.String(length=1024), nullable=False),
        sa.Column("canonical_root_path", sa.String(length=1024), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("profile_origin", sa.String(length=32), nullable=False),
        sa.Column("content_indexing_enabled", sa.Boolean(), server_default=sa.true()),
        sa.Column("metadata_only", sa.Boolean(), server_default=sa.false()),
        sa.Column("watcher_enabled", sa.Boolean(), server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_scan_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_sources_user_id", "memory_sources", ["user_id"])
    op.create_index(
        "ix_memory_sources_canonical_root_path", "memory_sources", ["canonical_root_path"]
    )
    op.create_index("ix_memory_sources_status", "memory_sources", ["status"])

    op.create_table(
        "memory_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("canonical_path", sa.String(length=2048), nullable=False),
        sa.Column("relative_path", sa.String(length=2048), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("extension", sa.String(length=32), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("indexing_state", sa.String(length=32), nullable=False),
        sa.Column("sensitivity", sa.String(length=32), server_default="local"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["memory_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_documents_user_id", "memory_documents", ["user_id"])
    op.create_index("ix_memory_documents_source_id", "memory_documents", ["source_id"])
    op.create_index("ix_memory_documents_canonical_path", "memory_documents", ["canonical_path"])
    op.create_index("ix_memory_documents_indexing_state", "memory_documents", ["indexing_state"])

    op.create_table(
        "memory_index_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["memory_documents.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["memory_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_index_jobs_user_id", "memory_index_jobs", ["user_id"])
    op.create_index("ix_memory_index_jobs_status", "memory_index_jobs", ["status"])

    op.create_table(
        "memory_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("project_root", sa.String(length=1024), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("sensitivity", sa.String(length=32), server_default="local"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_events_user_id", "memory_events", ["user_id"])
    op.create_index("ix_memory_events_event_type", "memory_events", ["event_type"])

    op.create_table(
        "memory_facts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("predicate", sa.String(length=128), nullable=False),
        sa.Column("object_summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.8"),
        sa.Column("source_event_id", sa.String(length=36), nullable=True),
        sa.Column("user_confirmed", sa.Boolean(), server_default=sa.false()),
        sa.Column("sensitivity", sa.String(length=32), server_default="local"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_facts_user_id", "memory_facts", ["user_id"])
    op.create_index("ix_memory_facts_subject", "memory_facts", ["subject"])

    op.create_table(
        "memory_entities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("aliases_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_entities_user_id", "memory_entities", ["user_id"])
    op.create_index("ix_memory_entities_canonical_name", "memory_entities", ["canonical_name"])

    op.create_table(
        "memory_relationships",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("source_entity_id", sa.String(length=36), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("target_entity_id", sa.String(length=36), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.7"),
        sa.Column("source_event_id", sa.String(length=36), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("project_root", sa.String(length=1024), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_confirmed", sa.Boolean(), server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_entity_id"], ["memory_entities.id"]),
        sa.ForeignKeyConstraint(["target_entity_id"], ["memory_entities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_relationships_user_id", "memory_relationships", ["user_id"])

    op.create_table(
        "memory_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("project_root", sa.String(length=1024), nullable=True),
        sa.Column("text_summary", sa.Text(), nullable=False),
        sa.Column("keyword_text", sa.Text(), nullable=True),
        sa.Column("embedding_json", sa.JSON(), nullable=True),
        sa.Column("sensitivity", sa.String(length=32), server_default="local"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["memory_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_chunks_user_id", "memory_chunks", ["user_id"])
    op.create_index("ix_memory_chunks_document_id", "memory_chunks", ["document_id"])

    op.create_table(
        "memory_project_summaries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=False),
        sa.Column("summary_type", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_event_ids_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_project_summaries_user_id", "memory_project_summaries", ["user_id"])

    op.create_table(
        "memory_retrieval_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("query_summary", sa.String(length=512), nullable=False),
        sa.Column("selected_memory_ids_json", sa.JSON(), nullable=True),
        sa.Column("scores_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_retrieval_logs_user_id", "memory_retrieval_logs", ["user_id"])

    op.create_table(
        "memory_permissions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("memory_type", sa.String(length=64), nullable=False),
        sa.Column("auto_store_allowed", sa.Boolean(), server_default=sa.true()),
        sa.Column("requires_confirmation", sa.Boolean(), server_default=sa.false()),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_permissions_user_id", "memory_permissions", ["user_id"])

    op.create_table(
        "memory_audit_chain",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("sanitized_payload_json", sa.JSON(), nullable=True),
        sa.Column("previous_hash", sa.String(length=128), nullable=False),
        sa.Column("current_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_memory_audit_chain_user_id", "memory_audit_chain", ["user_id"])


def downgrade() -> None:
    for table in (
        "memory_audit_chain",
        "memory_permissions",
        "memory_retrieval_logs",
        "memory_project_summaries",
        "memory_chunks",
        "memory_relationships",
        "memory_entities",
        "memory_facts",
        "memory_events",
        "memory_index_jobs",
        "memory_documents",
        "memory_sources",
        "memory_user_settings",
    ):
        op.drop_table(table)
