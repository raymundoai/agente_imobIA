"""Platform-managed agent configuration: the base prompt, its versions and per-tenant notes.

The platform team edits these from the admin panel. The newest prompt version is the one in
use; an empty prompt or model falls back to the built-in default and the server settings.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func, select
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.modules.ai.domain.ports import AgentConfigPort, AgentRuntimeConfig
from app.shared.database.base import Base

REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


class AgentPromptVersionModel(Base):
    __tablename__ = "agent_prompt_versions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    base_prompt: Mapped[str | None] = mapped_column(Text)
    chat_model: Mapped[str | None] = mapped_column(Text)
    reasoning_effort: Mapped[str | None] = mapped_column(Text)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text)
    created_by_email: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TenantAgentOverrideModel(Base):
    __tablename__ = "tenant_agent_overrides"

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    extra_instructions: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_email: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


def latest_prompt_version(session: Session) -> AgentPromptVersionModel | None:
    return session.scalars(
        select(AgentPromptVersionModel).order_by(AgentPromptVersionModel.created_at.desc()).limit(1)
    ).first()


class SqlAlchemyAgentConfigRepository(AgentConfigPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def for_tenant(self, tenant_id: UUID) -> AgentRuntimeConfig:
        version = latest_prompt_version(self._session)
        override = self._session.get(TenantAgentOverrideModel, tenant_id)
        return AgentRuntimeConfig(
            base_prompt=version.base_prompt if version else None,
            extra_instructions=override.extra_instructions if override else None,
            chat_model=version.chat_model if version else None,
            reasoning_effort=version.reasoning_effort if version else None,
            max_output_tokens=version.max_output_tokens if version else None,
        )
