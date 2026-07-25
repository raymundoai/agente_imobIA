from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from app.modules.integrations.ports.crm import (
    CreateDealData,
    CreateNoteData,
    CreateOrUpdateContactData,
    CreateTaskData,
    CrmCredentialsPort,
    CrmPort,
)
from app.modules.leads.domain.entities import LeadDemand, LeadDemandStatus, LeadPurpose
from app.modules.leads.ports.qualification import LeadQualificationPort
from app.modules.leads.ports.repositories import LeadDemandRepositoryPort
from app.modules.tenants.domain.entities import TenantStatus
from app.modules.tenants.ports.repositories import TenantRepositoryPort
from app.shared.errors.exceptions import ConfigurationError, NotFoundError
from app.shared.events.models import DomainEvent
from app.shared.events.ports import EventBusPort


class LeadQualificationService(LeadQualificationPort):
    def __init__(
        self,
        tenants: TenantRepositoryPort,
        leads: LeadDemandRepositoryPort,
        crm_credentials: CrmCredentialsPort,
        crm: CrmPort,
        events: EventBusPort,
    ) -> None:
        self._tenants = tenants
        self._leads = leads
        self._crm_credentials = crm_credentials
        self._crm = crm
        self._events = events

    def create_or_update_lead(
        self,
        tenant_id: UUID,
        data: dict[str, Any],
        *,
        conversation_id: UUID | None = None,
        handoff_reason: str | None = None,
    ) -> LeadDemand:
        tenant = self._tenants.get_by_id(tenant_id)
        if tenant is None or tenant.status is not TenantStatus.ACTIVE:
            raise NotFoundError("Tenant not found")
        phone = _as_str(data.get("phone"))
        if not phone:
            raise ValueError("Lead phone is required")
        lead = self._leads.get_open_by_phone(tenant_id, phone)
        if lead is None:
            lead = LeadDemand(
                tenant_id=tenant_id,
                lead_name=_as_str(data.get("lead_name") or data.get("name")) or phone,
                phone=phone,
            )
        self._apply_data(lead, data)
        lead.status = LeadDemandStatus.QUALIFIED

        credentials = self._crm_credentials.get(tenant.slug)
        if credentials is None:
            saved = (
                self._leads.update(tenant_id, lead)
                if self._leads.get_by_id(tenant_id, lead.id)
                else self._leads.create(tenant_id, lead)
            )
            self._publish_qualified(saved)
            return saved

        contact_data = CreateOrUpdateContactData(
            name=lead.lead_name,
            phone=lead.phone,
            email=_as_optional_str(data.get("email")),
        )
        contact = (
            self._crm.update_contact(credentials, lead.crm_contact_id, contact_data)
            if lead.crm_contact_id
            else self._crm.search_contact_by_phone(credentials, lead.phone)
        )
        if contact is None:
            contact = self._crm.create_contact(credentials, contact_data)
        lead.crm_contact_id = contact.id

        if lead.crm_deal_id is None:
            stage = credentials.stage_ids.get("qualified") or credentials.stage_ids.get("default")
            if not stage:
                raise ConfigurationError("HubSpot deal stage is not configured for tenant")
            deal = self._crm.create_deal(
                credentials,
                CreateDealData(
                    name=f"{lead.lead_name} - {lead.city or 'Demanda ImobIA'}",
                    pipeline=credentials.pipeline_id,
                    stage=stage,
                    amount=str(lead.price_max) if lead.price_max is not None else None,
                    properties=self._deal_properties(lead),
                ),
            )
            lead.crm_deal_id = deal.id
            self._crm.associate(credentials, "deal", deal.id, "contact", contact.id)

        saved = (
            self._leads.update(tenant_id, lead)
            if self._leads.get_by_id(tenant_id, lead.id)
            else self._leads.create(tenant_id, lead)
        )
        associations = [
            ("contact", saved.crm_contact_id),
            ("deal", saved.crm_deal_id),
        ]
        self._crm.add_note(
            credentials,
            CreateNoteData(
                body=self._summary(saved, conversation_id),
                timestamp=datetime.now(UTC),
                owner_id=credentials.owner_map.get("default"),
            ),
            [(kind, object_id) for kind, object_id in associations if object_id],
        )
        if handoff_reason:
            self._crm.create_task(
                credentials,
                CreateTaskData(
                    subject=f"Handoff ImobIA: {saved.lead_name}",
                    body=f"Motivo do handoff: {handoff_reason}",
                    timestamp=datetime.now(UTC) + timedelta(hours=2),
                    owner_id=credentials.owner_map.get("handoff")
                    or credentials.owner_map.get("default"),
                    priority="HIGH",
                ),
                [(kind, object_id) for kind, object_id in associations if object_id],
            )
        self._publish_qualified(saved)
        return saved

    def _publish_qualified(self, saved: LeadDemand) -> None:
        self._events.publish(
            DomainEvent(
                name="LeadQualified",
                tenant_id=saved.tenant_id,
                payload={
                    "lead_demand_id": str(saved.id),
                    "crm_contact_id": saved.crm_contact_id,
                    "crm_deal_id": saved.crm_deal_id,
                },
            )
        )

    @staticmethod
    def _apply_data(lead: LeadDemand, data: dict[str, Any]) -> None:
        lead.lead_name = _as_str(data.get("lead_name") or data.get("name")) or lead.lead_name
        lead.purpose = _purpose(data.get("purpose")) or lead.purpose
        lead.property_type = _as_optional_str(data.get("property_type")) or lead.property_type
        lead.city = _as_optional_str(data.get("city")) or lead.city
        neighborhoods = data.get("neighborhoods")
        if isinstance(neighborhoods, list):
            lead.neighborhoods = [str(item) for item in neighborhoods if str(item).strip()]
        lead.price_min = _decimal_or_none(data.get("price_min")) or lead.price_min
        lead.price_max = _decimal_or_none(data.get("price_max")) or lead.price_max
        lead.bedrooms = _int_or_none(data.get("bedrooms")) or lead.bedrooms
        lead.parking_spaces = _int_or_none(data.get("parking_spaces")) or lead.parking_spaces
        lead.min_area = _int_or_none(data.get("min_area")) or lead.min_area
        lead.notes = _as_optional_str(data.get("notes")) or lead.notes
        lead.updated_at = datetime.now(UTC)

    @staticmethod
    def _deal_properties(lead: LeadDemand) -> dict[str, Any]:
        return {
            "imobos_purpose": lead.purpose.value if lead.purpose else None,
            "imobos_city": lead.city,
            "imobos_property_type": lead.property_type,
            "imobos_bedrooms": str(lead.bedrooms) if lead.bedrooms is not None else None,
        }

    @staticmethod
    def _summary(lead: LeadDemand, conversation_id: UUID | None) -> str:
        return (
            "Lead qualificado pelo ImobIA.\n"
            f"Nome: {lead.lead_name}\n"
            f"Telefone: {lead.phone}\n"
            f"Finalidade: {lead.purpose.value if lead.purpose else '-'}\n"
            f"Cidade: {lead.city or '-'}\n"
            f"Bairros: {', '.join(lead.neighborhoods) if lead.neighborhoods else '-'}\n"
            f"Preço: {lead.price_min or '-'} a {lead.price_max or '-'}\n"
            f"Conversa: {conversation_id or '-'}\n"
            f"Observações: {lead.notes or '-'}"
        )


def _as_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _as_optional_str(value: Any) -> str | None:
    text = _as_str(value)
    return text or None


def _purpose(value: Any) -> LeadPurpose | None:
    if value is None:
        return None
    try:
        return LeadPurpose(str(value))
    except ValueError:
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
