from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.contacts.models import ContactModel
from app.modules.contacts.phone import normalize_contact_phone
from app.modules.contacts.ports import ContactReference


class ContactUpsertService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        tenant_id: UUID,
        *,
        phone: str,
        name: str | None,
        email: str | None = None,
        interest: str | None = None,
        notes: str | None = None,
        source: str | None = None,
    ) -> ContactReference:
        normalized = normalize_contact_phone(phone)
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"contact:{tenant_id}:{normalized}"},
        )
        model = self._session.scalar(
            select(ContactModel).where(
                ContactModel.tenant_id == tenant_id,
                ContactModel.phone == normalized,
            )
        )
        now = datetime.now(UTC)
        if model is None:
            model = ContactModel(
                id=uuid4(),
                tenant_id=tenant_id,
                name=(name or normalized).strip(),
                phone=normalized,
                email=email,
                kind="lead",
                status="active",
                tags=[source] if source else [],
                interest=interest,
                notes=notes,
                created_at=now,
                updated_at=now,
            )
            self._session.add(model)
        else:
            automated_source = source in {"whatsapp", "telegram"}
            can_update_qualified = (
                source == "qualification" and model.kind == "lead" and model.status == "active"
            )
            if (
                name
                and name.strip()
                and ((automated_source and model.name == model.phone) or can_update_qualified)
            ):
                model.name = name.strip()
            if email and (can_update_qualified or model.email is None):
                model.email = email
            if interest and model.interest is None:
                model.interest = interest
            if notes and model.notes is None:
                model.notes = notes
            if source and source not in model.tags:
                model.tags = [*model.tags, source]
            model.updated_at = now
        self._session.flush()
        return ContactReference(id=model.id, phone=model.phone)
