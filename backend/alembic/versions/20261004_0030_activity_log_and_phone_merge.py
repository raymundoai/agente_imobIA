"""Activity history, Brazilian numbers with country code, and merge of duplicate contacts.

One person could exist as several contacts: typed without the country code
("51991129452"), with it ("5551991129452"), or as WhatsApp reports some mobiles, without the
ninth digit ("555191129452"). Contacts with the same number are merged into the one that
holds the conversations, and short numbers are completed with 55. Every merge is recorded
in the new activity history with a copy of the removed contact.

Revision ID: 20261004_0030
Revises: 20261004_0029
"""

import json
import re
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20261004_0030"
down_revision = "20261004_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _complete(phone: str) -> str:
    return "55" + phone if re.fullmatch(r"[0-9]{10,11}", phone or "") else phone


def _identity_key(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) in (12, 13) and digits.startswith("55"):
        digits = digits[2:]
    if len(digits) == 11 and digits[2] == "9":
        digits = digits[:2] + digits[3:]
    return digits


def _merge(bind: sa.Connection, keeper: dict, loser: dict) -> None:
    """Folds a duplicate into the kept contact, filling only what the kept one is missing."""

    current = (
        bind.execute(
            sa.text("SELECT name, phone, notes FROM contacts WHERE id = :id"),
            {"id": keeper["id"]},
        )
        .mappings()
        .one()
    )
    notes = current["notes"]
    if loser["notes"] and loser["notes"] not in (notes or ""):
        notes = f"{notes}\n{loser['notes']}" if notes else loser["notes"]
    bind.execute(
        sa.text(
            "UPDATE contacts SET "
            "name = CASE WHEN name = phone THEN :name ELSE name END, "
            "email = COALESCE(email, :email), interest = COALESCE(interest, :interest), "
            "notes = :notes, tags = ARRAY(SELECT DISTINCT unnest(tags || CAST(:tags AS text[]))), "
            "kind = CASE WHEN kind = 'lead' AND :kind <> 'lead' THEN :kind ELSE kind END, "
            "created_at = LEAST(created_at, :created_at) WHERE id = :id"
        ),
        {
            "name": loser["name"],
            "email": loser["email"],
            "interest": loser["interest"],
            "notes": notes,
            "tags": list(loser["tags"] or []),
            "kind": loser["kind"],
            "created_at": loser["created_at"],
            "id": keeper["id"],
        },
    )
    for table in ("conversations", "lead_demands"):
        bind.execute(
            sa.text(f"UPDATE {table} SET contact_id = :keeper WHERE contact_id = :loser"),
            {"keeper": keeper["id"], "loser": loser["id"]},
        )
    bind.execute(sa.text("DELETE FROM contacts WHERE id = :id"), {"id": loser["id"]})
    snapshot = {
        key: str(value) if value is not None else None
        for key, value in loser.items()
        if key != "conversations"
    }
    snapshot["tags"] = list(loser["tags"] or [])
    bind.execute(
        sa.text(
            "INSERT INTO activity_logs (id, tenant_id, actor_type, entity, entity_id, action, "
            "summary, snapshot) VALUES (:id, :tenant, 'system', 'contact', :entity, 'merged', "
            ":summary, CAST(:snapshot AS jsonb))"
        ),
        {
            "id": uuid.uuid4(),
            "tenant": loser["tenant_id"],
            "entity": keeper["id"],
            "summary": (
                f"Contato {loser['name']} ({loser['phone']}) juntado com {current['name']} "
                f"({current['phone']}): é o mesmo número escrito de outra forma"
            ),
            "snapshot": json.dumps(snapshot, ensure_ascii=False),
        },
    )


def upgrade() -> None:
    op.create_table(
        "activity_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("actor_type", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_activity_logs_tenant_created", "activity_logs", ["tenant_id", "created_at"])

    bind = op.get_bind()
    contacts = (
        bind.execute(
            sa.text(
                "SELECT c.id, c.tenant_id, c.name, c.phone, c.email, c.kind, c.status, c.tags, "
                "c.interest, c.notes, c.created_at, "
                "(SELECT count(*) FROM conversations v WHERE v.contact_id = c.id) AS conversations "
                "FROM contacts c WHERE c.phone !~* '^telegram:' ORDER BY c.created_at"
            )
        )
        .mappings()
        .all()
    )
    groups: dict[tuple, list] = {}
    for contact in contacts:
        groups.setdefault((contact["tenant_id"], _identity_key(contact["phone"])), []).append(
            contact
        )
    for members in groups.values():
        # The number WhatsApp reports (the one with conversations) is kept as is.
        keeper = max(members, key=lambda item: (item["conversations"], len(item["phone"])))
        for loser in members:
            if loser["id"] != keeper["id"]:
                _merge(bind, keeper, loser)
        completed = _complete(keeper["phone"])
        if completed != keeper["phone"]:
            bind.execute(
                sa.text("UPDATE contacts SET phone = :phone WHERE id = :id"),
                {"phone": completed, "id": keeper["id"]},
            )

    demands = (
        bind.execute(
            sa.text(
                "SELECT id, tenant_id, lead_name, phone, status FROM lead_demands "
                "WHERE phone ~ '^[0-9]{10,11}$'"
            )
        )
        .mappings()
        .all()
    )
    for demand in demands:
        full = "55" + demand["phone"]
        clash = bind.execute(
            sa.text(
                "SELECT 1 FROM lead_demands WHERE tenant_id = :tenant AND phone = :phone "
                "AND status <> 'closed' AND id <> :id"
            ),
            {"tenant": demand["tenant_id"], "phone": full, "id": demand["id"]},
        ).first()
        # Only one open demand per number: a typed duplicate of an open one is closed.
        close = clash is not None and demand["status"] != "closed"
        bind.execute(
            sa.text(
                "UPDATE lead_demands SET phone = :phone, "
                "status = CASE WHEN :close THEN 'closed' ELSE status END WHERE id = :id"
            ),
            {"phone": full, "close": close, "id": demand["id"]},
        )
        if close:
            bind.execute(
                sa.text(
                    "INSERT INTO activity_logs (id, tenant_id, actor_type, entity, entity_id, "
                    "action, summary) VALUES (:id, :tenant, 'system', 'lead_demand', :entity, "
                    "'closed', :summary)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant": demand["tenant_id"],
                    "entity": demand["id"],
                    "summary": (
                        f"Demanda duplicada de {demand['lead_name']} encerrada: o mesmo número "
                        "já tinha uma demanda aberta"
                    ),
                },
            )


def downgrade() -> None:
    # Merged contacts are not split again; their copies remain in the history until dropped.
    op.drop_index("ix_activity_logs_tenant_created", table_name="activity_logs")
    op.drop_table("activity_logs")
