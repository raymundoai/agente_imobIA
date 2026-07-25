"""Add property media entities and cleanup outbox.

Revision ID: 20260725_0015
Revises: 20260725_0014
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260725_0015"
down_revision = "20260725_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "property_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_storage_key", sa.Text()),
        sa.Column("legacy_url", sa.Text()),
        sa.Column(
            "legacy_metadata",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("derived_storage_key", sa.Text()),
        sa.Column("original_name", sa.Text(), nullable=False),
        sa.Column("original_content_type", sa.Text(), nullable=False),
        sa.Column("original_size", sa.Integer(), nullable=False),
        sa.Column("derived_content_type", sa.Text()),
        sa.Column("derived_size", sa.Integer()),
        sa.Column("status", sa.Text(), server_default="uploaded", nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("optimization_prompt", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed')",
            name=op.f("ck_property_images_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "property_id"],
            ["properties.tenant_id", "properties.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_property_images_tenant_id_id"),
    )
    op.create_index(
        "ix_property_images_property_order",
        "property_images",
        ["tenant_id", "property_id", "sort_order"],
    )
    op.create_index(
        "uq_property_images_primary",
        "property_images",
        ["tenant_id", "property_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )
    op.execute(
        """
        INSERT INTO property_images (
            id, tenant_id, property_id, original_storage_key, legacy_url,
            legacy_metadata, original_name, original_content_type, original_size,
            status, is_primary, sort_order
        )
        SELECT
            md5(p.id::text || ':' || e.ordinality::text)::uuid,
            p.tenant_id,
            p.id,
            CASE
              WHEN (CASE WHEN jsonb_typeof(e.item) = 'string'
                    THEN trim(both '"' from e.item::text)
                    ELSE COALESCE(e.item->>'url', e.item->>'src') END)
                   LIKE '/media/properties/' || p.tenant_id::text || '/%'
              THEN substring(
                   (CASE WHEN jsonb_typeof(e.item) = 'string'
                    THEN trim(both '"' from e.item::text)
                    ELSE COALESCE(e.item->>'url', e.item->>'src') END)
                   FROM length('/media/properties/') + 1)
              ELSE NULL
            END,
            CASE WHEN jsonb_typeof(e.item) = 'string'
                 THEN trim(both '"' from e.item::text)
                 ELSE COALESCE(e.item->>'url', e.item->>'src') END,
            CASE WHEN jsonb_typeof(e.item) = 'object' THEN e.item
                 ELSE jsonb_build_object('legacy_value', e.item) END,
            COALESCE(NULLIF(e.item->>'original_name', ''), 'imagem-legada'),
            COALESCE(NULLIF(e.item->>'content_type', ''), 'application/octet-stream'),
            CASE WHEN COALESCE(e.item->>'size', '') ~ '^[0-9]+$'
                 THEN (e.item->>'size')::integer ELSE 0 END,
            'uploaded',
            e.ordinality = 1,
            e.ordinality - 1
        FROM properties p
        CROSS JOIN LATERAL jsonb_array_elements(p.images)
            WITH ORDINALITY AS e(item, ordinality)
        WHERE jsonb_typeof(p.images) = 'array'
        """
    )
    op.create_table(
        "property_image_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_key", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("derived_storage_key", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'failed', 'uncertain')",
            name=op.f("ck_property_image_operations_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "image_id"],
            ["property_images.tenant_id", "property_images.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_property_image_operations_id"),
    )
    op.create_index(
        "ix_property_image_operations_image",
        "property_image_operations",
        ["tenant_id", "image_id", "created_at"],
    )
    op.create_table(
        "property_media_cleanup",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('pending', 'done', 'failed')",
            name=op.f("ck_property_media_cleanup_status"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key", name="uq_property_media_cleanup_storage_key"),
    )
    op.create_index(
        "ix_property_media_cleanup_status",
        "property_media_cleanup",
        ["status", "created_at"],
    )
    # A coluna JSON anterior permanece somente como arquivo de compatibilidade.
    # Toda nova escrita e leitura operacional passa por property_images.
    op.execute(
        "COMMENT ON COLUMN properties.images IS "
        "'Deprecated read-only legacy archive; property_images is authoritative'"
    )


def downgrade() -> None:
    op.drop_table("property_media_cleanup")
    op.drop_table("property_image_operations")
    op.drop_table("property_images")
