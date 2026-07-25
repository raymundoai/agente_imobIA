from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.container import get_db_session
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.contacts.models import ContactModel
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


class ContactResponse(ContactPayload):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: ContactModel) -> "ContactResponse":
        return cls.model_validate(model, from_attributes=True)


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
    existing = session.scalar(
        select(ContactModel).where(
            ContactModel.tenant_id == principal.tenant_id,
            ContactModel.phone == payload.phone,
        )
    )
    if existing:
        raise ConflictError("A contact with this phone already exists")
    now = datetime.now(UTC)
    model = ContactModel(
        id=uuid4(),
        tenant_id=principal.tenant_id,
        **payload.model_dump(),
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
    for field, value in payload.model_dump().items():
        setattr(model, field, value)
    model.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(model)
    return ContactResponse.from_model(model)
