from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database.base import Base


class ConversationModel(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("channel IN ('whatsapp', 'telegram')", name="channel"),
        CheckConstraint("status IN ('open', 'waiting_human', 'closed')", name="status"),
        CheckConstraint("mode IN ('ai', 'human')", name="mode"),
        ForeignKeyConstraint(
            ["tenant_id", "assigned_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_conversations_tenant_assigned_user",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "contact_id"],
            ["contacts.tenant_id", "contacts.id"],
            name="fk_conversations_tenant_contact",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_conversations_tenant_id_id"),
        Index("ix_conversations_tenant_id", "tenant_id"),
        Index(
            "ix_conversations_tenant_status_last_message",
            "tenant_id",
            "status",
            sql_text("last_message_at DESC"),
        ),
        Index(
            "uq_conversations_active_phone",
            "tenant_id",
            "channel",
            "phone",
            unique=True,
            postgresql_where=sql_text("status <> 'closed'"),
        ),
        Index(
            "ix_conversations_tenant_assigned_user",
            "tenant_id",
            "assigned_user_id",
            postgresql_where=sql_text("assigned_user_id IS NOT NULL"),
        ),
        Index("ix_conversations_tenant_contact", "tenant_id", "contact_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_conversations_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(
        Text, nullable=False, default="whatsapp", server_default="whatsapp"
    )
    external_contact_id: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    customer_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open", server_default="open")
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="ai", server_default="ai")
    current_intent: Mapped[str | None] = mapped_column(Text)
    current_agent: Mapped[str] = mapped_column(
        Text, nullable=False, default="leads", server_default="leads"
    )
    assigned_user_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("direction IN ('inbound', 'outbound')", name="direction"),
        CheckConstraint("author_type IN ('customer', 'ai', 'human', 'system')", name="author_type"),
        ForeignKeyConstraint(
            ["tenant_id", "conversation_id"],
            ["conversations.tenant_id", "conversations.id"],
            name="fk_messages_tenant_conversation",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_messages_tenant_id_id"),
        Index("ix_messages_tenant_id", "tenant_id"),
        Index(
            "ix_messages_tenant_conversation_created",
            "tenant_id",
            "conversation_id",
            "created_at",
        ),
        Index(
            "uq_messages_tenant_channel_external_id",
            "tenant_id",
            "channel",
            "external_message_id",
            unique=True,
            postgresql_where=sql_text("external_message_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    conversation_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(
        Text, nullable=False, default="whatsapp", server_default="whatsapp"
    )
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    author_type: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=sql_text("'[]'::jsonb")
    )
    external_message_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
