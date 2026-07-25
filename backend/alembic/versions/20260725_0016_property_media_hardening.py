"""Harden property media installations that already ran revision 0015.

Revision ID: 20260725_0016
Revises: 20260725_0015
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260725_0016"
down_revision = "20260725_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    image_columns = {column["name"] for column in inspector.get_columns("property_images")}
    if "legacy_url" not in image_columns:
        op.add_column("property_images", sa.Column("legacy_url", sa.Text()))
    if "legacy_metadata" not in image_columns:
        op.add_column(
            "property_images",
            sa.Column(
                "legacy_metadata",
                postgresql.JSONB(),
                server_default=sa.text("'{}'::jsonb"),
                nullable=False,
            ),
        )
    original = next(
        column
        for column in inspector.get_columns("property_images")
        if column["name"] == "original_storage_key"
    )
    if not original["nullable"]:
        op.alter_column("property_images", "original_storage_key", nullable=True)

    cleanup_columns = {
        column["name"] for column in inspector.get_columns("property_media_cleanup")
    }
    if "attempts" not in cleanup_columns:
        op.add_column(
            "property_media_cleanup",
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        )
    if "available_at" not in cleanup_columns:
        op.add_column(
            "property_media_cleanup",
            sa.Column(
                "available_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

    # Idempotente: completa o backfill em bancos nos quais a primeira versão de
    # 0015 foi aplicada antes de a compatibilidade legada existir.
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
        ON CONFLICT (tenant_id, id) DO NOTHING
        """
    )

    if "property_image_operations" not in inspector.get_table_names():
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
                "status IN ('processing', 'ready', 'failed', 'uncertain')"
            ),
            sa.ForeignKeyConstraint(
                ["tenant_id", "image_id"],
                ["property_images.tenant_id", "property_images.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "tenant_id", "id", name="uq_property_image_operations_id"
            ),
        )
        op.create_index(
            "ix_property_image_operations_image",
            "property_image_operations",
            ["tenant_id", "image_id", "created_at"],
        )


def downgrade() -> None:
    # A revisão é corretiva e preserva dados; rollback destrutivo é deliberadamente
    # evitado. O downgrade estrutural completo continua pertencendo à revisão 0015.
    pass
