from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.leads.adapters.models import LeadDemandModel
from app.modules.leads.adapters.repositories import _to_domain as lead_to_domain
from app.modules.leads.domain.entities import LeadDemand, LeadPurpose
from app.modules.properties.adapters.models import PropertyDemandMatchModel, PropertyModel
from app.modules.properties.application.matching import calculate_property_match
from app.modules.properties.domain.entities import Property, PropertyPurpose
from app.modules.properties.ports.repositories import PropertyRepositoryPort


def _to_domain(model: PropertyModel) -> Property:
    return Property(
        id=model.id,
        tenant_id=model.tenant_id,
        source=model.source,
        source_url=model.source_url,
        title=model.title,
        city=model.city,
        neighborhood=model.neighborhood,
        price=model.price,
        sale_price=model.sale_price,
        rent_price=model.rent_price,
        purpose=PropertyPurpose(model.purpose) if model.purpose else None,
        property_type=model.property_type,
        category=model.category,
        status=model.status,
        listing_code=model.listing_code,
        description=model.description,
        bedrooms=model.bedrooms,
        suites=model.suites,
        bathrooms=model.bathrooms,
        parking_spaces=model.parking_spaces,
        area=model.area,
        land_area=model.land_area,
        address=model.address,
        details=model.details,
        images=model.images,
        advertiser_name=model.advertiser_name,
        advertiser_phone=model.advertiser_phone,
        via_extension=model.via_extension,
        duplicate_group_id=model.duplicate_group_id,
        content_hash=model.content_hash,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlAlchemyPropertyRepository(PropertyRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_captured(
        self,
        tenant_id: UUID,
        property: Property,
        demand_id: UUID | None,
        *,
        commit: bool = True,
    ) -> Property:
        if property.tenant_id != tenant_id:
            raise ValueError("Property tenant does not match repository scope")
        existing = self._find_duplicate(tenant_id, property)
        if existing is None:
            model = PropertyModel.from_domain(property)
            self._session.add(model)
            self._session.flush()
        else:
            model = existing
            model.source = property.source
            model.title = property.title
            model.city = property.city
            model.neighborhood = property.neighborhood
            model.price = property.price
            model.sale_price = property.sale_price
            model.rent_price = property.rent_price
            model.purpose = property.purpose.value if property.purpose else None
            model.property_type = property.property_type
            model.category = property.category
            model.status = property.status
            model.listing_code = property.listing_code
            model.description = property.description
            model.bedrooms = property.bedrooms
            model.suites = property.suites
            model.bathrooms = property.bathrooms
            model.parking_spaces = property.parking_spaces
            model.area = property.area
            model.land_area = property.land_area
            model.address = property.address
            model.details = property.details
            model.images = property.images
            model.advertiser_name = property.advertiser_name
            model.advertiser_phone = property.advertiser_phone
            model.via_extension = property.via_extension
            model.content_hash = property.content_hash
            model.updated_at = datetime.now(UTC)
            self._session.flush()
        if demand_id is not None:
            self._link(tenant_id, model.id, demand_id)
        if commit:
            self._session.commit()
            self._session.refresh(model)
        else:
            self._session.flush()
        return _to_domain(model)

    def create_manual(self, tenant_id: UUID, property: Property) -> Property:
        if property.tenant_id != tenant_id:
            raise ValueError("Property tenant does not match repository scope")
        model = PropertyModel.from_domain(property)
        self._session.add(model)
        self._session.commit()
        self._session.refresh(model)
        return _to_domain(model)

    def get_by_id(self, tenant_id: UUID, property_id: UUID) -> Property | None:
        model = self._session.scalar(
            select(PropertyModel).where(
                PropertyModel.tenant_id == tenant_id,
                PropertyModel.id == property_id,
            )
        )
        return _to_domain(model) if model else None

    def list(
        self,
        tenant_id: UUID,
        *,
        demand_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Property]:
        statement = select(PropertyModel).where(PropertyModel.tenant_id == tenant_id)
        if demand_id is not None:
            statement = statement.join(
                PropertyDemandMatchModel,
                (PropertyDemandMatchModel.tenant_id == PropertyModel.tenant_id)
                & (PropertyDemandMatchModel.property_id == PropertyModel.id),
            ).where(PropertyDemandMatchModel.demand_id == demand_id)
        models = self._session.scalars(
            statement.order_by(PropertyModel.created_at.desc(), PropertyModel.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_domain(model) for model in models]

    def search_matching(
        self,
        tenant_id: UUID,
        demand: LeadDemand,
        limit: int = 50,
        *,
        internal_only: bool = False,
    ) -> list[Property]:
        statement = select(PropertyModel).where(
            PropertyModel.tenant_id == tenant_id,
            PropertyModel.status == "active",
        )
        if internal_only:
            statement = statement.where(PropertyModel.source == "manual")
        models = self._session.scalars(
            statement.order_by(PropertyModel.created_at.desc(), PropertyModel.id)
        ).all()
        matches = [calculate_property_match(_to_domain(model), demand) for model in models]
        matches = [match for match in matches if match.score >= 50]
        matches.sort(key=lambda match: match.score, reverse=True)
        return [match.property for match in matches[:limit]]

    def search_by_filters(
        self,
        tenant_id: UUID,
        *,
        city: str | None = None,
        purpose: str | None = None,
        property_type: str | None = None,
        neighborhoods: list[str] | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        bedrooms: int | None = None,
        parking_spaces: int | None = None,
        internal_only: bool = False,
        limit: int = 5,
    ) -> list[Property]:
        demand = LeadDemand(
            tenant_id=tenant_id,
            lead_name="Busca do agente",
            phone="internal",
            city=city,
            purpose=LeadPurpose(purpose) if purpose in {"buy", "rent"} else None,
            property_type=property_type,
            neighborhoods=neighborhoods or [],
            price_min=price_min,
            price_max=price_max,
            bedrooms=bedrooms,
            parking_spaces=parking_spaces,
        )
        return self.search_matching(
            tenant_id,
            demand,
            limit=limit,
            internal_only=internal_only,
        )

    def _find_duplicate(self, tenant_id: UUID, property: Property) -> PropertyModel | None:
        if property.source_url:
            existing = self._session.scalar(
                select(PropertyModel).where(
                    PropertyModel.tenant_id == tenant_id,
                    PropertyModel.source_url == property.source_url,
                )
            )
            if existing:
                return existing
        if property.content_hash:
            return self._session.scalar(
                select(PropertyModel).where(
                    PropertyModel.tenant_id == tenant_id,
                    PropertyModel.content_hash == property.content_hash,
                )
            )
        return None

    def _link(self, tenant_id: UUID, property_id: UUID, demand_id: UUID) -> None:
        demand = self._session.get(LeadDemandModel, demand_id)
        property_model = self._session.get(PropertyModel, property_id)
        score = 100
        if demand is not None and property_model is not None and demand.tenant_id == tenant_id:
            score = calculate_property_match(
                _to_domain(property_model), lead_to_domain(demand)
            ).score
        statement = (
            insert(PropertyDemandMatchModel)
            .values(
                id=uuid4(),
                tenant_id=tenant_id,
                property_id=property_id,
                demand_id=demand_id,
                match_score=score,
            )
            .on_conflict_do_nothing(
                constraint="uq_property_demand_match",
            )
        )
        self._session.execute(statement)
