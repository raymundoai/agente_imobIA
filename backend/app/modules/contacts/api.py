from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.activity.service import model_snapshot, record_activity
from app.modules.auth.api.dependencies import (
    CurrentPrincipal,
    get_current_principal,
    require_roles,
)
from app.modules.contacts.models import ContactModel
from app.modules.contacts.phone import (
    normalize_contact_phone,
    phone_identity_key,
    phone_variants,
)
from app.modules.conversations.adapters.models import ConversationModel
from app.modules.leads.adapters.models import LeadDemandModel
from app.modules.tenants.adapters.models import TenantModel
from app.modules.users.domain.entities import UserRole
from app.shared.errors.exceptions import ConflictError, NotFoundError

router = APIRouter(prefix="/contacts", tags=["contacts"])


class ContactPayload(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=8, max_length=40)
    email: EmailStr | None = None
    kind: str = Field(pattern="^(lead|tenant|owner|client)$")
    status: str = Field(default="active", pattern="^(active|inactive)$")
    tags: list[str] = Field(default_factory=list, max_length=50)
    interest: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=10000)

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, value: str) -> str:
        return normalize_contact_phone(value)


class ContactResponse(ContactPayload):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ContactModel) -> "ContactResponse":
        return cls.model_validate(model, from_attributes=True)


class ContactProfilePictureResponse(BaseModel):
    url: str | None


@router.get("", response_model=list[ContactResponse])
def list_contacts(
    query: str | None = None,
    kind: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[ContactResponse]:
    statement = select(ContactModel).where(ContactModel.tenant_id == principal.tenant_id)
    if kind:
        statement = statement.where(ContactModel.kind == kind)
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                ContactModel.name.ilike(pattern),
                ContactModel.phone.ilike(pattern),
                ContactModel.email.ilike(pattern),
            )
        )
    models = session.scalars(statement.order_by(ContactModel.name).limit(limit)).all()
    return [ContactResponse.from_model(model) for model in models]


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactPayload,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ContactResponse:
    normalized_phone = normalize_contact_phone(payload.phone)
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"contact:{principal.tenant_id}:{phone_identity_key(normalized_phone)}"},
    )
    existing = session.scalar(
        select(ContactModel).where(
            ContactModel.tenant_id == principal.tenant_id,
            ContactModel.phone.in_(phone_variants(normalized_phone)),
        )
    )
    if existing:
        raise ConflictError("A contact with this phone already exists")
    now = datetime.now(UTC)
    model = ContactModel(
        id=uuid4(),
        tenant_id=principal.tenant_id,
        **{**payload.model_dump(), "phone": normalized_phone},
        created_at=now,
        updated_at=now,
    )
    session.add(model)
    session.commit()
    session.refresh(model)
    return ContactResponse.from_model(model)


@router.patch("/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: UUID,
    payload: ContactPayload,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> ContactResponse:
    model = session.scalar(
        select(ContactModel).where(
            ContactModel.tenant_id == principal.tenant_id, ContactModel.id == contact_id
        )
    )
    if model is None:
        raise NotFoundError("Contact not found")
    values = payload.model_dump()
    values["phone"] = normalize_contact_phone(payload.phone)
    if values["phone"] != model.phone:
        linked = session.scalar(
            select(ConversationModel.id)
            .where(
                ConversationModel.tenant_id == principal.tenant_id,
                ConversationModel.contact_id == contact_id,
            )
            .union(
                select(LeadDemandModel.id).where(
                    LeadDemandModel.tenant_id == principal.tenant_id,
                    LeadDemandModel.contact_id == contact_id,
                )
            )
            .limit(1)
        )
        if linked is not None:
            raise ConflictError(
                "O telefone de um contato vinculado não pode ser alterado; crie outro contato."
            )
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"contact:{principal.tenant_id}:{values['phone']}"},
        )
    duplicate = session.scalar(
        select(ContactModel).where(
            ContactModel.tenant_id == principal.tenant_id,
            ContactModel.phone.in_(phone_variants(values["phone"])),
            ContactModel.id != contact_id,
        )
    )
    if duplicate:
        raise ConflictError("A contact with this phone already exists")
    for field, value in values.items():
        setattr(model, field, value)
    model.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(model)
    return ContactResponse.from_model(model)


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: UUID,
    principal: CurrentPrincipal = Depends(require_roles(UserRole.ADMIN, UserRole.GESTOR)),
    session: Session = Depends(get_db_session),
) -> None:
    """Removes the contact card. Conversations and demands stay, without the link to it."""

    model = session.scalar(
        select(ContactModel).where(
            ContactModel.tenant_id == principal.tenant_id, ContactModel.id == contact_id
        )
    )
    if model is None:
        raise NotFoundError("Contact not found")
    detached = {}
    for label, table in (("conversa", ConversationModel), ("demanda", LeadDemandModel)):
        result = session.execute(
            update(table)
            .where(table.tenant_id == principal.tenant_id, table.contact_id == contact_id)
            .values(contact_id=None)
        )
        detached[label] = result.rowcount or 0
    kept = [
        f"{count} {label}{'s' if count > 1 else ''}" for label, count in detached.items() if count
    ]
    record_activity(
        session,
        tenant_id=principal.tenant_id,
        actor_user_id=principal.user_id,
        entity="contact",
        entity_id=model.id,
        action="deleted",
        summary=f"Contato excluído: {model.name}"
        + (
            f" ({' e '.join(kept)} {'continua' if sum(detached.values()) == 1 else 'continuam'}"
            " no sistema)"
            if kept
            else ""
        ),
        snapshot=model_snapshot(model),
    )
    session.delete(model)
    session.commit()


@router.get("/{contact_id}/profile-picture", response_model=ContactProfilePictureResponse)
def get_contact_profile_picture(
    contact_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
    container: Container = Depends(get_container),
) -> ContactProfilePictureResponse:
    model = session.scalar(
        select(ContactModel).where(
            ContactModel.tenant_id == principal.tenant_id,
            ContactModel.id == contact_id,
        )
    )
    if model is None:
        raise NotFoundError("Contato não encontrado")
    tenant_slug = session.scalar(
        select(TenantModel.slug).where(TenantModel.id == principal.tenant_id)
    )
    credentials = container.channel_credentials.get(tenant_slug) if tenant_slug else None
    resolver = getattr(container.message_channel, "profile_picture_url", None)
    url = resolver(credentials, model.phone) if credentials and callable(resolver) else None
    return ContactProfilePictureResponse(url=url)
