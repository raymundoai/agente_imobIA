from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql_text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.properties.domain.entities import Property, PropertyDemandMatch
from app.shared.database.base import Base


class PropertyModel(Base):
    __tablename__ = "properties"
    __table_args__ = (
        CheckConstraint("purpose IN ('buy', 'rent', 'both') OR purpose IS NULL", name="purpose"),
        CheckConstraint("category IN ('residential', 'commercial', 'mixed')", name="category"),
        CheckConstraint("status IN ('draft', 'active', 'inactive')", name="status"),
        UniqueConstraint("tenant_id", "id", name="uq_properties_tenant_id_id"),
        Index("ix_properties_tenant_city", "tenant_id", "city"),
        Index("ix_properties_tenant_filters", "tenant_id", "purpose", "property_type", "city"),
        Index(
            "uq_properties_tenant_listing_code",
            "tenant_id",
            "listing_code",
            unique=True,
            postgresql_where=sql_text("listing_code IS NOT NULL"),
        ),
        Index(
            "uq_properties_tenant_source_url",
            "tenant_id",
            "source_url",
            unique=True,
            postgresql_where=sql_text("source_url IS NOT NULL"),
        ),
        Index(
            "uq_properties_tenant_content_hash",
            "tenant_id",
            "content_hash",
            unique=True,
            postgresql_where=sql_text("content_hash IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_properties_tenant_id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(Text, nullable=False)
    neighborhood: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    rent_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    purpose: Mapped[str | None] = mapped_column(Text)
    property_type: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(
        Text, nullable=False, default="residential", server_default="residential"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="active", server_default="active"
    )
    listing_code: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    suites: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    parking_spaces: Mapped[int | None] = mapped_column(Integer)
    area: Mapped[int | None] = mapped_column(Integer)
    land_area: Mapped[int | None] = mapped_column(Integer)
    address: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    images: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=sql_text("'[]'::jsonb"),
        comment="Deprecated read-only legacy archive; property_images is authoritative",
    )
    advertiser_name: Mapped[str | None] = mapped_column(Text)
    advertiser_phone: Mapped[str | None] = mapped_column(Text)
    via_extension: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    duplicate_group_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    content_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    @classmethod
    def from_domain(cls, property_: Property) -> "PropertyModel":
        return cls(
            id=property_.id,
            tenant_id=property_.tenant_id,
            source=property_.source,
            source_url=property_.source_url,
            title=property_.title,
            city=property_.city,
            neighborhood=property_.neighborhood,
            price=property_.price,
            sale_price=property_.sale_price,
            rent_price=property_.rent_price,
            purpose=property_.purpose.value if property_.purpose else None,
            property_type=property_.property_type,
            category=property_.category,
            status=property_.status,
            listing_code=property_.listing_code,
            description=property_.description,
            bedrooms=property_.bedrooms,
            suites=property_.suites,
            bathrooms=property_.bathrooms,
            parking_spaces=property_.parking_spaces,
            area=property_.area,
            land_area=property_.land_area,
            address=property_.address,
            details=property_.details,
            images=property_.images,
            advertiser_name=property_.advertiser_name,
            advertiser_phone=property_.advertiser_phone,
            via_extension=property_.via_extension,
            duplicate_group_id=property_.duplicate_group_id,
            content_hash=property_.content_hash,
            created_at=property_.created_at,
            updated_at=property_.updated_at,
        )


class PropertyDemandMatchModel(Base):
    __tablename__ = "property_demand_matches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "property_id"],
            ["properties.tenant_id", "properties.id"],
            name="fk_property_matches_tenant_property",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "demand_id"],
            ["lead_demands.tenant_id", "lead_demands.id"],
            name="fk_property_matches_tenant_demand",
            ondelete="CASCADE",
        ),
        UniqueConstraint("tenant_id", "property_id", "demand_id", name="uq_property_demand_match"),
        Index("ix_property_matches_tenant_demand", "tenant_id", "demand_id"),
        Index("ix_property_matches_tenant_property", "tenant_id", "property_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    property_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    demand_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    match_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @classmethod
    def from_domain(cls, match: PropertyDemandMatch) -> "PropertyDemandMatchModel":
        return cls(
            id=match.id,
            tenant_id=match.tenant_id,
            property_id=match.property_id,
            demand_id=match.demand_id,
            match_score=match.match_score,
            created_at=match.created_at,
        )


class PropertyImageModel(Base):
    __tablename__ = "property_images"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "property_id"],
            ["properties.tenant_id", "properties.id"],
            name="fk_property_images_tenant_property",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed')",
            name="status",
        ),
        UniqueConstraint("tenant_id", "id", name="uq_property_images_tenant_id_id"),
        Index("ix_property_images_property_order", "tenant_id", "property_id", "sort_order"),
        Index(
            "uq_property_images_primary",
            "tenant_id",
            "property_id",
            unique=True,
            postgresql_where=sql_text("is_primary"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    property_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    original_storage_key: Mapped[str | None] = mapped_column(Text)
    legacy_url: Mapped[str | None] = mapped_column(Text)
    legacy_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=sql_text("'{}'::jsonb")
    )
    derived_storage_key: Mapped[str | None] = mapped_column(Text)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    original_content_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_size: Mapped[int] = mapped_column(Integer, nullable=False)
    derived_content_type: Mapped[str | None] = mapped_column(Text)
    derived_size: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="uploaded", server_default="uploaded"
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    optimization_prompt: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PropertyMediaCleanupModel(Base):
    __tablename__ = "property_media_cleanup"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done', 'failed')", name="status"),
        UniqueConstraint("storage_key", name="uq_property_media_cleanup_storage_key"),
        Index("ix_property_media_cleanup_status", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending", server_default="pending"
    )
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PropertyImageOperationModel(Base):
    __tablename__ = "property_image_operations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "image_id"],
            ["property_images.tenant_id", "property_images.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "status IN ('processing', 'ready', 'failed', 'uncertain')", name="status"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_property_image_operations_id"),
        Index("ix_property_image_operations_image", "tenant_id", "image_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    image_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    reservation_key: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    derived_storage_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
