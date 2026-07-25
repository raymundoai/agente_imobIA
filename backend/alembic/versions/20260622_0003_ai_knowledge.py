"""Create AI knowledge base and audit log tables.

Revision ID: 20260622_0003
Revises: 20260622_0002
Create Date: 2026-06-22
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260622_0003"
down_revision = "20260622_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("file_type", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'indexing', 'indexed', 'error')",
            name=op.f("ck_knowledge_documents_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_knowledge_documents_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "uploaded_by"],
            ["users.tenant_id", "users.id"],
            name="fk_knowledge_documents_tenant_uploaded_by",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_documents")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_knowledge_documents_tenant_id_id"),
    )
    op.create_index(
        "ix_knowledge_documents_tenant_status", "knowledge_documents", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_knowledge_documents_tenant_created",
        "knowledge_documents",
        ["tenant_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "document_id"],
            ["knowledge_documents.tenant_id", "knowledge_documents.id"],
            name="fk_knowledge_chunks_tenant_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_chunks")),
    )
    op.execute(
        "ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1536) "
        "USING embedding::vector(1536)"
    )
    op.create_index(
        "ix_knowledge_chunks_tenant_document",
        "knowledge_chunks",
        ["tenant_id", "document_id"],
    )
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "ai_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("detected_intent", sa.Text(), nullable=True),
        sa.Column(
            "tools_called",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "chunks_used",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("handoff_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_ai_audit_logs_tenant_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_ai_audit_logs_tenant_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_audit_logs")),
    )
    op.create_index(
        "ix_ai_audit_logs_tenant_created",
        "ai_audit_logs",
        ["tenant_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_ai_audit_logs_tenant_conversation",
        "ai_audit_logs",
        ["tenant_id", "conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_audit_logs_tenant_conversation", table_name="ai_audit_logs")
    op.drop_index("ix_ai_audit_logs_tenant_created", table_name="ai_audit_logs")
    op.drop_table("ai_audit_logs")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.drop_index("ix_knowledge_chunks_tenant_document", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("ix_knowledge_documents_tenant_created", table_name="knowledge_documents")
    op.drop_index("ix_knowledge_documents_tenant_status", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
