from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.leads.adapters.models import LeadDemandModel
from app.modules.leads.domain.entities import LeadDemand, LeadDemandStatus, LeadPurpose
from app.modules.leads.ports.repositories import LeadDemandRepositoryPort


def _to_domain(model: LeadDemandModel) -> LeadDemand:
    return LeadDemand(
        id=model.id,
        tenant_id=model.tenant_id,
        contact_id=model.contact_id,
        conversation_id=model.conversation_id,
        lead_name=model.lead_name,
        phone=model.phone,
        purpose=LeadPurpose(model.purpose) if model.purpose else None,
        property_type=model.property_type,
        city=model.city,
        state=model.state,
        neighborhoods=model.neighborhoods,
        price_min=model.price_min,
        price_max=model.price_max,
        bedrooms=model.bedrooms,
        parking_spaces=model.parking_spaces,
        min_area=model.min_area,
        notes=model.notes,
        status=LeadDemandStatus(model.status),
        responsible_user_id=model.responsible_user_id,
        crm_contact_id=model.crm_contact_id,
        crm_deal_id=model.crm_deal_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyLeadDemandRepository(LeadDemandRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_phone(self, tenant_id: UUID, phone: str) -> None:
        self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"lead-demand:{tenant_id}:{phone}"},
        )

    def create(self, tenant_id: UUID, lead: LeadDemand) -> LeadDemand:
        if lead.tenant_id != tenant_id:
            raise ValueError("Lead tenant does not match repository scope")
        model = LeadDemandModel.from_domain(lead)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def get_by_id(self, tenant_id: UUID, lead_id: UUID) -> LeadDemand | None:
        model = self._session.scalar(
            select(LeadDemandModel).where(
                LeadDemandModel.tenant_id == tenant_id,
                LeadDemandModel.id == lead_id,
            )
        )
        return _to_domain(model) if model else None

    def get_open_by_phone(self, tenant_id: UUID, phone: str) -> LeadDemand | None:
        model = self._session.scalar(
            select(LeadDemandModel).where(
                LeadDemandModel.tenant_id == tenant_id,
                LeadDemandModel.phone == phone,
                LeadDemandModel.status != LeadDemandStatus.CLOSED.value,
            )
        )
        return _to_domain(model) if model else None

    def update(self, tenant_id: UUID, lead: LeadDemand) -> LeadDemand:
        model = self._session.scalar(
            select(LeadDemandModel).where(
                LeadDemandModel.tenant_id == tenant_id,
                LeadDemandModel.id == lead.id,
            )
        )
        if model is None:
            raise ValueError("Lead does not exist in tenant scope")
        model.lead_name = lead.lead_name
        model.contact_id = lead.contact_id
        model.conversation_id = lead.conversation_id
        model.phone = lead.phone
        model.purpose = lead.purpose.value if lead.purpose else None
        model.property_type = lead.property_type
        model.city = lead.city
        model.state = lead.state
        model.neighborhoods = lead.neighborhoods
        model.price_min = lead.price_min
        model.price_max = lead.price_max
        model.bedrooms = lead.bedrooms
        model.parking_spaces = lead.parking_spaces
        model.min_area = lead.min_area
        model.notes = lead.notes
        model.status = lead.status.value
        model.responsible_user_id = lead.responsible_user_id
        model.crm_contact_id = lead.crm_contact_id
        model.crm_deal_id = lead.crm_deal_id
        model.updated_at = lead.updated_at
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def delete(self, tenant_id: UUID, lead_id: UUID) -> bool:
        model = self._session.scalar(
            select(LeadDemandModel).where(
                LeadDemandModel.tenant_id == tenant_id,
                LeadDemandModel.id == lead_id,
            )
        )
        if model is None:
            return False
        self._session.delete(model)
        self._session.commit()
        return True

    def list(
        self,
        tenant_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
        contact_id: UUID | None = None,
    ) -> list[LeadDemand]:
        statement = select(LeadDemandModel).where(LeadDemandModel.tenant_id == tenant_id)
        if contact_id is not None:
            statement = statement.where(LeadDemandModel.contact_id == contact_id)
        models = self._session.scalars(
            statement
            .order_by(LeadDemandModel.created_at.desc(), LeadDemandModel.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_domain(model) for model in models]
