"""Link contacts, conversations, and lead demands.

Revision ID: 20260725_0012
Revises: 20260725_0011
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260725_0012"
down_revision = "20260725_0011"
branch_labels = None
depends_on = None

PHONE_SQL = """
CASE
  WHEN lower(trim(phone)) LIKE 'telegram:%'
    AND trim(split_part(trim(phone), ':', 2)) ~ '^[0-9]{1,20}$'
    THEN 'telegram:' || trim(split_part(trim(phone), ':', 2))
  WHEN length(regexp_replace(phone, '\\D', '', 'g')) BETWEEN 10 AND 15
    THEN regexp_replace(phone, '\\D', '', 'g')
  ELSE trim(phone)
END
"""


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TEMP TABLE contact_merge_map ON COMMIT DROP AS
        SELECT id AS duplicate_id, first_value(id) OVER (
            PARTITION BY tenant_id, ({PHONE_SQL})
            ORDER BY
              (kind <> 'lead') DESC,
              (status = 'inactive') DESC,
              ((email IS NOT NULL)::int + (interest IS NOT NULL)::int + (notes IS NOT NULL)::int)
                DESC,
              updated_at DESC,
              created_at,
              id
          ) AS survivor_id
        FROM contacts
        """
    )
    op.execute(
        """
        UPDATE contacts survivor SET
          email = coalesce(survivor.email, (
            SELECT source.email FROM contact_merge_map mapping
            JOIN contacts source ON source.id = mapping.duplicate_id
            WHERE mapping.survivor_id = survivor.id AND source.email IS NOT NULL
            ORDER BY source.updated_at DESC LIMIT 1
          )),
          interest = coalesce(survivor.interest, (
            SELECT source.interest FROM contact_merge_map mapping
            JOIN contacts source ON source.id = mapping.duplicate_id
            WHERE mapping.survivor_id = survivor.id AND source.interest IS NOT NULL
            ORDER BY source.updated_at DESC LIMIT 1
          )),
          notes = coalesce(survivor.notes, (
            SELECT source.notes FROM contact_merge_map mapping
            JOIN contacts source ON source.id = mapping.duplicate_id
            WHERE mapping.survivor_id = survivor.id AND source.notes IS NOT NULL
            ORDER BY source.updated_at DESC LIMIT 1
          )),
          tags = coalesce((
            SELECT array_agg(DISTINCT tag)
            FROM contact_merge_map mapping
            JOIN contacts source ON source.id = mapping.duplicate_id
            CROSS JOIN LATERAL unnest(source.tags) tag
            WHERE mapping.survivor_id = survivor.id
          ), survivor.tags)
        WHERE survivor.id IN (SELECT survivor_id FROM contact_merge_map)
        """
    )
    op.execute(
        """
        DELETE FROM contacts contact
        USING contact_merge_map mapping
        WHERE contact.id = mapping.duplicate_id
          AND mapping.duplicate_id <> mapping.survivor_id
        """
    )
    op.execute(f"UPDATE contacts SET phone = ({PHONE_SQL})")

    op.execute(
        f"""
        WITH ranked AS (
          SELECT id, row_number() OVER (
            PARTITION BY tenant_id, channel, ({PHONE_SQL})
            ORDER BY last_message_at DESC, started_at DESC, id
          ) AS position
          FROM conversations
          WHERE status <> 'closed'
        )
        UPDATE conversations
        SET status = 'closed', closed_at = coalesce(closed_at, now())
        WHERE id IN (SELECT id FROM ranked WHERE position > 1)
        """
    )
    op.execute(f"UPDATE conversations SET phone = ({PHONE_SQL})")

    op.execute(
        f"""
        WITH ranked AS (
          SELECT id, row_number() OVER (
            PARTITION BY tenant_id, ({PHONE_SQL})
            ORDER BY updated_at DESC, created_at DESC, id
          ) AS position
          FROM lead_demands
          WHERE status <> 'closed'
        )
        UPDATE lead_demands
        SET status = 'closed', updated_at = now()
        WHERE id IN (SELECT id FROM ranked WHERE position > 1)
        """
    )
    op.execute(f"UPDATE lead_demands SET phone = ({PHONE_SQL})")

    op.add_column(
        "conversations", sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "lead_demands", sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "lead_demands", sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True)
    )

    op.execute(
        """
        INSERT INTO contacts (
          id, tenant_id, name, phone, email, kind, status, tags, interest, notes,
          created_at, updated_at
        )
        SELECT
          gen_random_uuid(), tenant_id, coalesce(max(customer_name), phone), phone, NULL,
          'lead', 'active', array_agg(DISTINCT channel)::text[], NULL, NULL,
          min(started_at), max(last_message_at)
        FROM conversations
        GROUP BY tenant_id, phone
        ON CONFLICT (tenant_id, phone) DO UPDATE
        SET
          tags = (
            SELECT ARRAY(SELECT DISTINCT value FROM unnest(contacts.tags || EXCLUDED.tags) value)
          ),
          updated_at = greatest(contacts.updated_at, EXCLUDED.updated_at)
        """
    )
    op.execute(
        """
        INSERT INTO contacts (
          id, tenant_id, name, phone, email, kind, status, tags, interest, notes,
          created_at, updated_at
        )
        SELECT DISTINCT ON (tenant_id, phone)
          gen_random_uuid(), tenant_id, lead_name, phone, NULL, 'lead', 'active',
          ARRAY['qualification']::text[], NULL, notes, created_at, updated_at
        FROM lead_demands
        ORDER BY tenant_id, phone, updated_at DESC, created_at DESC, id
        ON CONFLICT (tenant_id, phone) DO UPDATE
        SET
          notes = coalesce(contacts.notes, EXCLUDED.notes),
          tags = (
            SELECT ARRAY(SELECT DISTINCT value FROM unnest(
              contacts.tags || EXCLUDED.tags
            ) value)
          ),
          updated_at = greatest(contacts.updated_at, EXCLUDED.updated_at)
        """
    )
    op.execute(
        """
        UPDATE conversations conversation
        SET contact_id = contact.id
        FROM contacts contact
        WHERE contact.tenant_id = conversation.tenant_id
          AND contact.phone = conversation.phone
        """
    )
    op.execute(
        """
        UPDATE lead_demands demand
        SET contact_id = contact.id
        FROM contacts contact
        WHERE contact.tenant_id = demand.tenant_id
          AND contact.phone = demand.phone
        """
    )
    op.create_foreign_key(
        "fk_conversations_tenant_contact",
        "conversations",
        "contacts",
        ["tenant_id", "contact_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_lead_demands_tenant_contact",
        "lead_demands",
        "contacts",
        ["tenant_id", "contact_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_lead_demands_tenant_conversation",
        "lead_demands",
        "conversations",
        ["tenant_id", "conversation_id"],
        ["tenant_id", "id"],
    )
    op.create_index("ix_conversations_tenant_contact", "conversations", ["tenant_id", "contact_id"])
    op.create_index("ix_lead_demands_tenant_contact", "lead_demands", ["tenant_id", "contact_id"])
    op.create_index(
        "ix_lead_demands_tenant_conversation",
        "lead_demands",
        ["tenant_id", "conversation_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_demands_tenant_conversation", table_name="lead_demands")
    op.drop_index("ix_lead_demands_tenant_contact", table_name="lead_demands")
    op.drop_index("ix_conversations_tenant_contact", table_name="conversations")
    op.drop_constraint(
        "fk_lead_demands_tenant_conversation", "lead_demands", type_="foreignkey"
    )
    op.drop_constraint("fk_lead_demands_tenant_contact", "lead_demands", type_="foreignkey")
    op.drop_constraint("fk_conversations_tenant_contact", "conversations", type_="foreignkey")
    op.drop_column("lead_demands", "conversation_id")
    op.drop_column("lead_demands", "contact_id")
    op.drop_column("conversations", "contact_id")
