import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, BinaryIO
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.container import Container, get_container, get_db_session
from app.modules.ai.domain.ports import (
    AiProviderDispatchUncertainError,
    AiProviderRejectedError,
)
from app.modules.auth.api.dependencies import CurrentPrincipal, get_current_principal
from app.modules.billing_usage.service import (
    CreditLedgerService,
    estimated_image_charge,
    image_token_charge,
)
from app.modules.properties.adapters.models import (
    PropertyImageModel,
    PropertyImageOperationModel,
    PropertyMediaCleanupModel,
    PropertyMediaStagingModel,
    PropertyModel,
)
from app.modules.properties.adapters.repositories import (
    SqlAlchemyPropertyRepository,
    _to_domain,
)
from app.modules.properties.application.use_cases import ListPropertiesUseCase
from app.modules.properties.domain.entities import Property, PropertyPurpose
from app.modules.properties.media import (
    ALLOWED_IMAGE_TYPES,
    LocalPropertyImageStorage,
    PropertyImageUpload,
    optimization_prompt,
    validate_property_image,
    validate_property_media,
)

router = APIRouter(prefix="/properties", tags=["properties"])


def _stream_file(stream: BinaryIO, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    try:
        while chunk := stream.read(chunk_size):
            yield chunk
    finally:
        stream.close()


class PropertyResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    source: str
    source_url: str | None
    title: str
    city: str
    neighborhood: str | None
    price: Decimal | None
    sale_price: Decimal | None
    rent_price: Decimal | None
    purpose: str | None
    property_type: str | None
    category: str
    status: str
    listing_code: str | None
    description: str | None
    bedrooms: int | None
    suites: int | None
    bathrooms: int | None
    parking_spaces: int | None
    area: int | None
    land_area: int | None
    address: dict[str, Any]
    details: dict[str, Any]
    images: list[dict[str, Any]]
    advertiser_name: str | None
    advertiser_phone: str | None
    via_extension: bool

    @classmethod
    def from_domain(cls, property_: Property) -> "PropertyResponse":
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
            # Compatibilidade de contrato: a coleção operacional é consultada
            # exclusivamente em /properties/{id}/images.
            images=[],
            advertiser_name=property_.advertiser_name,
            advertiser_phone=property_.advertiser_phone,
            via_extension=property_.via_extension,
        )


class PropertyAddressRequest(BaseModel):
    street: str = Field(min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=40)
    complement: str | None = Field(default=None, max_length=120)
    neighborhood: str = Field(min_length=1, max_length=120)
    city: str = Field(min_length=1, max_length=120)
    state: str = Field(min_length=2, max_length=2)
    postal_code: str | None = Field(default=None, max_length=12)


class PropertyDetailsRequest(BaseModel):
    condo_fee: Decimal | None = Field(default=None, ge=0)
    property_tax: Decimal | None = Field(default=None, ge=0)
    fire_insurance: Decimal | None = Field(default=None, ge=0)
    built_area: Decimal | None = Field(default=None, ge=0)
    usable_area: Decimal | None = Field(default=None, ge=0)
    total_area: Decimal | None = Field(default=None, ge=0)
    furnished: bool = False
    pet_friendly: bool = False
    accepts_financing: bool = False
    accepts_exchange: bool = False
    rental_guarantees: list[str] = Field(default_factory=list, max_length=20)
    minimum_lease_months: int | None = Field(default=None, ge=1, le=120)
    floor: int | None = Field(default=None, ge=0)
    unit: str | None = Field(default=None, max_length=40)
    year_built: int | None = Field(default=None, ge=1800, le=2200)
    rooms: list[str] = Field(default_factory=list, max_length=80)
    amenities: list[str] = Field(default_factory=list, max_length=120)


class CreatePropertyRequest(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    listing_code: str | None = Field(default=None, max_length=80)
    purpose: str = Field(pattern="^(buy|rent|both)$")
    property_type: str = Field(min_length=2, max_length=80)
    category: str = Field(pattern="^(residential|commercial|mixed)$")
    status: str = Field(default="active", pattern="^(draft|active|inactive)$")
    sale_price: Decimal | None = Field(default=None, ge=0)
    rent_price: Decimal | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=20000)
    bedrooms: int | None = Field(default=None, ge=0, le=100)
    suites: int | None = Field(default=None, ge=0, le=100)
    bathrooms: int | None = Field(default=None, ge=0, le=100)
    parking_spaces: int | None = Field(default=None, ge=0, le=100)
    area: int | None = Field(default=None, ge=0)
    land_area: int | None = Field(default=None, ge=0)
    address: PropertyAddressRequest
    details: PropertyDetailsRequest = Field(default_factory=PropertyDetailsRequest)
    owner_name: str | None = Field(default=None, max_length=200)
    owner_phone: str | None = Field(default=None, max_length=40)
    source_url: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_offer_prices(self) -> "CreatePropertyRequest":
        if self.purpose in {"buy", "both"} and self.sale_price is None:
            raise ValueError("sale_price is required for properties offered for sale")
        if self.purpose in {"rent", "both"} and self.rent_price is None:
            raise ValueError("rent_price is required for rental properties")
        if self.suites is not None and self.bedrooms is not None and self.suites > self.bedrooms:
            raise ValueError("suites cannot exceed bedrooms")
        return self


class LinkedPropertyImageResponse(BaseModel):
    id: UUID
    property_id: UUID
    original_name: str
    status: str
    is_primary: bool
    sort_order: int
    original_size: int
    original_content_type: str
    media_type: str
    derived_size: int | None
    original_url: str
    display_url: str
    error: str | None


class PropertyStatusRequest(BaseModel):
    status: str = Field(pattern="^(active|inactive)$")


class PropertyImageUpdateRequest(BaseModel):
    is_primary: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)


class PropertyImageOrderItem(BaseModel):
    id: UUID
    sort_order: int = Field(ge=0, le=10000)


class PropertyImageOrderRequest(BaseModel):
    images: list[PropertyImageOrderItem] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_unique_ids_and_orders(self) -> "PropertyImageOrderRequest":
        ids = [item.id for item in self.images]
        orders = [item.sort_order for item in self.images]
        if len(ids) != len(set(ids)):
            raise ValueError("image ids must be unique")
        if len(orders) != len(set(orders)):
            raise ValueError("sort orders must be unique")
        return self


class ReprocessImageRequest(BaseModel):
    operation_id: UUID = Field(default_factory=uuid4)
    optimizations: list[str] = Field(default_factory=list, max_length=10)
    note: str | None = Field(default=None, max_length=1000)


class StagedPropertyMediaResponse(BaseModel):
    id: UUID
    original_name: str
    content_type: str
    size: int


class CommitStagedPropertyMediaRequest(BaseModel):
    staging_ids: list[UUID] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> "CommitStagedPropertyMediaRequest":
        if len(self.staging_ids) != len(set(self.staging_ids)):
            raise ValueError("staging ids must be unique")
        return self




@router.post("", response_model=PropertyResponse, status_code=status.HTTP_201_CREATED)
def create_property(
    payload: CreatePropertyRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PropertyResponse:
    data = payload.model_dump(mode="python")
    address = data["address"]
    details = data["details"]
    property_ = Property(
        tenant_id=principal.tenant_id,
        source="manual",
        source_url=payload.source_url,
        title=payload.title,
        listing_code=payload.listing_code,
        city=address["city"],
        neighborhood=address["neighborhood"],
        price=payload.sale_price or payload.rent_price,
        sale_price=payload.sale_price,
        rent_price=payload.rent_price,
        purpose=PropertyPurpose(payload.purpose),
        property_type=payload.property_type,
        category=payload.category,
        status=payload.status,
        description=payload.description,
        bedrooms=payload.bedrooms,
        suites=payload.suites,
        bathrooms=payload.bathrooms,
        parking_spaces=payload.parking_spaces,
        area=payload.area,
        land_area=payload.land_area,
        address=address,
        details=details,
        images=[],
        advertiser_name=payload.owner_name,
        advertiser_phone=payload.owner_phone,
    )
    saved = SqlAlchemyPropertyRepository(session).create_manual(principal.tenant_id, property_)
    return PropertyResponse.from_domain(saved)


@router.get("", response_model=list[PropertyResponse])
def list_properties(
    demand_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[PropertyResponse]:
    properties = ListPropertiesUseCase(SqlAlchemyPropertyRepository(session)).execute(
        principal.tenant_id, demand_id=demand_id, limit=limit, offset=offset
    )
    return [PropertyResponse.from_domain(item) for item in properties]


def _property_model(session: Session, tenant_id: UUID, property_id: UUID) -> PropertyModel:
    model = session.scalar(
        select(PropertyModel).where(
            PropertyModel.tenant_id == tenant_id,
            PropertyModel.id == property_id,
        )
    )
    if model is None:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")
    return model


def _image_model(
    session: Session, tenant_id: UUID, property_id: UUID, image_id: UUID
) -> PropertyImageModel:
    model = session.scalar(
        select(PropertyImageModel).where(
            PropertyImageModel.tenant_id == tenant_id,
            PropertyImageModel.property_id == property_id,
            PropertyImageModel.id == image_id,
        )
    )
    if model is None:
        raise HTTPException(status_code=404, detail="Imagem não encontrada.")
    return model


def _linked_image_response(image: PropertyImageModel) -> LinkedPropertyImageResponse:
    base = f"/properties/{image.property_id}/images/{image.id}/content"
    return LinkedPropertyImageResponse(
        id=image.id,
        property_id=image.property_id,
        original_name=image.original_name,
        status=image.status,
        is_primary=image.is_primary,
        sort_order=image.sort_order,
        original_size=image.original_size,
        original_content_type=image.original_content_type,
        media_type=("image" if image.original_content_type.startswith("image/") else "video"),
        derived_size=image.derived_size,
        original_url=f"{base}?variant=original",
        display_url=f"{base}?variant=display",
        error=image.error,
    )


@router.get("/{property_id}", response_model=PropertyResponse)
def get_property(
    property_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PropertyResponse:
    model = _property_model(session, principal.tenant_id, property_id)
    return PropertyResponse.from_domain(_to_domain(model))


@router.put("/{property_id}", response_model=PropertyResponse)
def update_property(
    property_id: UUID,
    payload: CreatePropertyRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PropertyResponse:
    model = _property_model(session, principal.tenant_id, property_id)
    data = payload.model_dump(mode="python")
    address = data.pop("address")
    details = data.pop("details")
    model.title = data["title"]
    model.listing_code = data["listing_code"]
    model.purpose = data["purpose"]
    model.property_type = data["property_type"]
    model.category = data["category"]
    model.status = data["status"]
    model.sale_price = data["sale_price"]
    model.rent_price = data["rent_price"]
    model.price = data["sale_price"] or data["rent_price"]
    model.description = data["description"]
    model.bedrooms = data["bedrooms"]
    model.suites = data["suites"]
    model.bathrooms = data["bathrooms"]
    model.parking_spaces = data["parking_spaces"]
    model.area = data["area"]
    model.land_area = data["land_area"]
    model.address = address
    model.city = address["city"]
    model.neighborhood = address["neighborhood"]
    model.details = details
    model.advertiser_name = data["owner_name"]
    model.advertiser_phone = data["owner_phone"]
    model.source_url = data["source_url"]
    model.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(model)
    return PropertyResponse.from_domain(_to_domain(model))


@router.patch("/{property_id}/status", response_model=PropertyResponse)
def set_property_status(
    property_id: UUID,
    payload: PropertyStatusRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> PropertyResponse:
    model = _property_model(session, principal.tenant_id, property_id)
    model.status = payload.status
    model.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(model)
    return PropertyResponse.from_domain(_to_domain(model))


@router.delete("/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_property(
    property_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> None:
    model = _property_model(session, principal.tenant_id, property_id)
    if model.status != "inactive":
        raise HTTPException(
            status_code=409,
            detail="Inative o imóvel antes de excluí-lo definitivamente.",
        )
    keys = [
        key
        for key in session.scalars(
        select(PropertyImageModel.original_storage_key).where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_id,
            PropertyImageModel.original_storage_key.is_not(None),
        )
        ).all()
        if key
    ]
    keys += [
        key
        for key in session.scalars(
            select(PropertyImageModel.derived_storage_key).where(
                PropertyImageModel.tenant_id == principal.tenant_id,
                PropertyImageModel.property_id == property_id,
                PropertyImageModel.derived_storage_key.is_not(None),
            )
        ).all()
        if key
    ]
    for key in keys:
        session.add(
            PropertyMediaCleanupModel(
                id=uuid4(), tenant_id=principal.tenant_id, storage_key=key
            )
        )
    session.delete(model)
    session.commit()


@router.get("/{property_id}/images", response_model=list[LinkedPropertyImageResponse])
def list_property_images(
    property_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[LinkedPropertyImageResponse]:
    _property_model(session, principal.tenant_id, property_id)
    images = session.scalars(
        select(PropertyImageModel)
        .where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_id,
        )
        .order_by(PropertyImageModel.sort_order, PropertyImageModel.created_at)
    ).all()
    return [_linked_image_response(image) for image in images]


@router.post(
    "/media/staging",
    response_model=StagedPropertyMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def stage_property_media(
    file: Annotated[UploadFile, File(description="Mídia temporária do imóvel")],
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> StagedPropertyMediaResponse:
    content_type = (file.content_type or "").lower()
    max_bytes = (
        container.settings.property_video_max_bytes
        if content_type.startswith("video/")
        else container.settings.property_image_max_bytes
    )
    upload = PropertyImageUpload(
        original_name=Path(file.filename or "midia").name,
        content_type=content_type,
        content=await file.read(max_bytes + 1),
    )
    try:
        validate_property_media(
            upload,
            max_image_bytes=container.settings.property_image_max_bytes,
            max_video_bytes=container.settings.property_video_max_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    staging_id = uuid4()
    key = LocalPropertyImageStorage.build_key(
        principal.tenant_id, staging_id, staging_id, "staging", upload.content_type
    )
    container.property_image_storage.put(
        principal.tenant_id, key, upload.content, upload.content_type
    )
    staged = PropertyMediaStagingModel(
        id=staging_id,
        tenant_id=principal.tenant_id,
        storage_key=key,
        original_name=upload.original_name,
        content_type=upload.content_type,
        size=len(upload.content),
    )
    try:
        session.add(staged)
        session.commit()
    except Exception:
        session.rollback()
        container.property_image_storage.delete(principal.tenant_id, key)
        raise
    return StagedPropertyMediaResponse(
        id=staged.id,
        original_name=staged.original_name,
        content_type=staged.content_type,
        size=staged.size,
    )


@router.delete("/media/staging/{staging_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_staged_property_media(
    staging_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> None:
    staged = session.scalar(
        select(PropertyMediaStagingModel).where(
            PropertyMediaStagingModel.tenant_id == principal.tenant_id,
            PropertyMediaStagingModel.id == staging_id,
        )
    )
    if staged is None:
        return
    container.property_image_storage.delete(principal.tenant_id, staged.storage_key)
    session.delete(staged)
    session.commit()


@router.post(
    "/{property_id}/images/commit",
    response_model=list[LinkedPropertyImageResponse],
    status_code=status.HTTP_201_CREATED,
)
def commit_staged_property_media(
    property_id: UUID,
    payload: CommitStagedPropertyMediaRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> list[LinkedPropertyImageResponse]:
    property_model = _property_model(session, principal.tenant_id, property_id)
    session.execute(
        select(PropertyModel.id)
        .where(PropertyModel.id == property_model.id)
        .with_for_update()
    )
    staged_by_id = {
        item.id: item
        for item in session.scalars(
            select(PropertyMediaStagingModel)
            .where(
                PropertyMediaStagingModel.tenant_id == principal.tenant_id,
                PropertyMediaStagingModel.id.in_(payload.staging_ids),
            )
            .with_for_update()
        ).all()
    }
    if len(staged_by_id) != len(payload.staging_ids):
        raise HTTPException(status_code=404, detail="Uma ou mais mídias temporárias expiraram.")
    current_count = session.scalar(
        select(func.count()).select_from(PropertyImageModel).where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_id,
        )
    ) or 0
    max_sort_order = session.scalar(
        select(func.max(PropertyImageModel.sort_order)).where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_id,
        )
    )
    next_sort_order = (max_sort_order if max_sort_order is not None else -1) + 1
    if current_count + len(payload.staging_ids) > container.settings.property_image_max_files:
        raise HTTPException(status_code=422, detail="O imóvel excederia o limite de mídias.")
    has_primary_image = bool(
        session.scalar(
            select(PropertyImageModel.id).where(
                PropertyImageModel.tenant_id == principal.tenant_id,
                PropertyImageModel.property_id == property_id,
                PropertyImageModel.is_primary.is_(True),
            )
        )
    )
    created: list[PropertyImageModel] = []
    new_keys: list[str] = []
    try:
        for index, staging_id in enumerate(payload.staging_ids):
            staged = staged_by_id[staging_id]
            image_id = uuid4()
            new_key = LocalPropertyImageStorage.build_key(
                principal.tenant_id,
                property_id,
                image_id,
                "original",
                staged.content_type,
            )
            with container.property_image_storage.open(
                principal.tenant_id, staged.storage_key
            ) as source:
                content = source.read()
            container.property_image_storage.put(
                principal.tenant_id, new_key, content, staged.content_type
            )
            new_keys.append(new_key)
            is_primary = (
                not has_primary_image
                and not any(item.is_primary for item in created)
                and staged.content_type in ALLOWED_IMAGE_TYPES
            )
            image = PropertyImageModel(
                id=image_id,
                tenant_id=principal.tenant_id,
                property_id=property_id,
                original_storage_key=new_key,
                original_name=staged.original_name,
                original_content_type=staged.content_type,
                original_size=staged.size,
                status="uploaded",
                is_primary=is_primary,
                sort_order=next_sort_order + index,
            )
            session.add(image)
            session.delete(staged)
            created.append(image)
        session.commit()
    except Exception:
        session.rollback()
        for key in new_keys:
            container.property_image_storage.delete(principal.tenant_id, key)
        raise
    for staging_id in payload.staging_ids:
        container.property_image_storage.delete(
            principal.tenant_id, staged_by_id[staging_id].storage_key
        )
    return [_linked_image_response(image) for image in created]


@router.post(
    "/{property_id}/images",
    response_model=list[LinkedPropertyImageResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_property_images(
    property_id: UUID,
    files: Annotated[
        list[UploadFile],
        File(description="Imagens JPEG, PNG ou WebP, ou vídeos MP4, MOV ou WebM"),
    ],
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> list[LinkedPropertyImageResponse]:
    property_model = _property_model(session, principal.tenant_id, property_id)
    session.execute(
        select(PropertyModel.id)
        .where(PropertyModel.id == property_model.id)
        .with_for_update()
    )
    if not files or len(files) > container.settings.property_image_max_files:
        raise HTTPException(status_code=422, detail="Quantidade de mídias inválida.")
    current_count = session.scalar(
        select(func.count()).select_from(PropertyImageModel).where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_id,
        )
    ) or 0
    max_sort_order = session.scalar(
        select(func.max(PropertyImageModel.sort_order)).where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_id,
        )
    )
    next_sort_order = (max_sort_order if max_sort_order is not None else -1) + 1
    if current_count + len(files) > container.settings.property_image_max_files:
        raise HTTPException(status_code=422, detail="O imóvel excederia o limite de mídias.")
    created: list[PropertyImageModel] = []
    stored_keys: list[str] = []
    has_primary_image = bool(
        session.scalar(
            select(PropertyImageModel.id).where(
                PropertyImageModel.tenant_id == principal.tenant_id,
                PropertyImageModel.property_id == property_id,
                PropertyImageModel.is_primary.is_(True),
            )
        )
    )
    try:
        for index, file in enumerate(files):
            content_type = (file.content_type or "").lower()
            max_bytes = (
                container.settings.property_video_max_bytes
                if content_type.startswith("video/")
                else container.settings.property_image_max_bytes
            )
            upload = PropertyImageUpload(
                original_name=Path(file.filename or "midia").name,
                content_type=content_type,
                content=await file.read(max_bytes + 1),
            )
            try:
                validate_property_media(
                    upload,
                    max_image_bytes=container.settings.property_image_max_bytes,
                    max_video_bytes=container.settings.property_video_max_bytes,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            image_id = uuid4()
            key = LocalPropertyImageStorage.build_key(
                principal.tenant_id, property_id, image_id, "original", upload.content_type
            )
            container.property_image_storage.put(
                principal.tenant_id, key, upload.content, upload.content_type
            )
            stored_keys.append(key)
            is_primary = (
                not has_primary_image
                and not any(item.is_primary for item in created)
                and upload.content_type in ALLOWED_IMAGE_TYPES
            )
            image = PropertyImageModel(
                id=image_id,
                tenant_id=principal.tenant_id,
                property_id=property_id,
                original_storage_key=key,
                original_name=upload.original_name,
                original_content_type=upload.content_type,
                original_size=len(upload.content),
                status="uploaded",
                is_primary=is_primary,
                sort_order=next_sort_order + index,
            )
            session.add(image)
            created.append(image)
        session.commit()
    except Exception:
        session.rollback()
        for key in stored_keys:
            container.property_image_storage.delete(principal.tenant_id, key)
        raise
    return [_linked_image_response(image) for image in created]


@router.get("/{property_id}/images/{image_id}/content")
def property_image_content(
    property_id: UUID,
    image_id: UUID,
    variant: Annotated[str, Query(pattern="^(original|display)$")] = "display",
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
):
    image = _image_model(session, principal.tenant_id, property_id, image_id)
    derived = variant == "display" and image.derived_storage_key is not None
    key = image.derived_storage_key if derived else image.original_storage_key
    content_type = image.derived_content_type if derived else image.original_content_type
    if key is None:
        parsed = urlparse(image.legacy_url or "")
        allowed_hosts = {
            host.lower() for host in container.settings.property_legacy_url_allowed_hosts
        }
        if (
            image.legacy_url
            and parsed.scheme == "https"
            and parsed.hostname
            and parsed.hostname.lower() in allowed_hosts
        ):
            return RedirectResponse(image.legacy_url)
        raise HTTPException(
            status_code=404,
            detail="Mídia legada preservada, mas sua origem não é confiável ou acessível.",
        )
    signed = container.property_image_storage.signed_url(principal.tenant_id, key)
    if signed:
        return RedirectResponse(signed)
    try:
        stream = container.property_image_storage.open(principal.tenant_id, key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Arquivo da mídia não encontrado.") from exc
    content_size = image.derived_size if derived else image.original_size
    return StreamingResponse(
        _stream_file(stream),
        media_type=content_type,
        headers={
            "Content-Length": str(content_size),
            "Cache-Control": "private, max-age=300",
        },
    )


@router.put(
    "/{property_id}/images/order",
    response_model=list[LinkedPropertyImageResponse],
)
def reorder_property_images(
    property_id: UUID,
    payload: PropertyImageOrderRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[LinkedPropertyImageResponse]:
    property_model = session.scalar(
        select(PropertyModel)
        .where(
            PropertyModel.tenant_id == principal.tenant_id,
            PropertyModel.id == property_id,
        )
        .with_for_update()
    )
    if property_model is None:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")
    images = session.scalars(
        select(PropertyImageModel)
        .where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_id,
        )
        .with_for_update()
    ).all()
    current_ids = {image.id for image in images}
    requested_ids = {item.id for item in payload.images}
    if requested_ids != current_ids:
        raise HTTPException(
            status_code=409,
            detail="A ordenação deve conter exatamente todas as imagens atuais do imóvel.",
        )
    order_by_id = {item.id: item.sort_order for item in payload.images}
    for image in images:
        image.sort_order = order_by_id[image.id]
        image.updated_at = datetime.now(UTC)
    session.commit()
    ordered = sorted(images, key=lambda item: (item.sort_order, item.created_at, item.id))
    return [_linked_image_response(image) for image in ordered]


@router.patch(
    "/{property_id}/images/{image_id}", response_model=LinkedPropertyImageResponse
)
def update_property_image(
    property_id: UUID,
    image_id: UUID,
    payload: PropertyImageUpdateRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> LinkedPropertyImageResponse:
    property_model = _property_model(session, principal.tenant_id, property_id)
    session.execute(
        select(PropertyModel.id)
        .where(PropertyModel.id == property_model.id)
        .with_for_update()
    )
    image = _image_model(session, principal.tenant_id, property_id, image_id)
    if payload.is_primary:
        if image.original_content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=422,
                detail="Somente imagens podem ser definidas como capa do imóvel.",
            )
        session.execute(
            update(PropertyImageModel)
            .where(
                PropertyImageModel.tenant_id == principal.tenant_id,
                PropertyImageModel.property_id == property_id,
                PropertyImageModel.id != image_id,
            )
            .values(is_primary=False)
        )
        image.is_primary = True
    elif payload.is_primary is False:
        if image.is_primary:
            raise HTTPException(
                status_code=409,
                detail="Defina outra imagem como principal antes de remover esta marcação.",
            )
        image.is_primary = False
    if payload.sort_order is not None:
        image.sort_order = payload.sort_order
    image.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(image)
    return _linked_image_response(image)
@router.delete(
    "/{property_id}/images/{image_id}",
    response_model=list[LinkedPropertyImageResponse],
)
def delete_property_image(
    property_id: UUID,
    image_id: UUID,
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_db_session),
) -> list[LinkedPropertyImageResponse]:
    property_model = session.scalar(
        select(PropertyModel)
        .where(
            PropertyModel.tenant_id == principal.tenant_id,
            PropertyModel.id == property_id,
        )
        .with_for_update()
    )
    if property_model is None:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado.")
    images = session.scalars(
        select(PropertyImageModel)
        .where(
            PropertyImageModel.tenant_id == principal.tenant_id,
            PropertyImageModel.property_id == property_id,
        )
        .order_by(PropertyImageModel.sort_order, PropertyImageModel.created_at)
        .with_for_update()
    ).all()
    image = next((item for item in images if item.id == image_id), None)
    if image is None:
        raise HTTPException(status_code=404, detail="Imagem não encontrada.")
    remaining = [item for item in images if item.id != image_id]
    remaining_images = [
        item for item in remaining if item.original_content_type in ALLOWED_IMAGE_TYPES
    ]
    if image.is_primary and remaining_images:
        # A restrição parcial de principal único é imediata no PostgreSQL.
        # Desmarcar e flushar dentro da mesma transação libera a chave antes
        # de promover a substituta, sem expor o estado intermediário.
        image.is_primary = False
        session.flush()
        remaining_images[0].is_primary = True
        remaining_images[0].updated_at = datetime.now(UTC)
    keys = [key for key in [image.original_storage_key] if key]
    if image.derived_storage_key:
        keys.append(image.derived_storage_key)
    for key in keys:
        session.add(
            PropertyMediaCleanupModel(
                id=uuid4(), tenant_id=principal.tenant_id, storage_key=key
            )
        )
    session.delete(image)
    session.commit()
    return [_linked_image_response(item) for item in remaining]


@router.post(
    "/{property_id}/images/{image_id}/reprocess",
    response_model=LinkedPropertyImageResponse,
)
def reprocess_property_image(
    property_id: UUID,
    image_id: UUID,
    payload: ReprocessImageRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    container: Container = Depends(get_container),
    session: Session = Depends(get_db_session),
) -> LinkedPropertyImageResponse:
    image = _image_model(session, principal.tenant_id, property_id, image_id)
    if image.original_content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=422,
            detail="A otimização com IA está disponível somente para imagens.",
        )
    if container.ai_provider is None:
        raise HTTPException(status_code=503, detail="A integração OpenAI não está configurada.")
    if image.original_storage_key is None:
        raise HTTPException(
            status_code=422,
            detail="Imagem legada sem original local; faça um novo upload antes de tratar.",
        )
    prompt = optimization_prompt(payload.optimizations, payload.note)
    with container.property_image_storage.open(
        principal.tenant_id, image.original_storage_key
    ) as source:
        original = source.read()
    reservation_key = f"property-image-reprocess:{image.id}:{payload.operation_id}"
    existing_operation = session.scalar(
        select(PropertyImageOperationModel).where(
            PropertyImageOperationModel.tenant_id == principal.tenant_id,
            PropertyImageOperationModel.id == payload.operation_id,
        )
    )
    if existing_operation is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Operação já registrada com status {existing_operation.status}.",
        )
    operation = PropertyImageOperationModel(
        id=payload.operation_id,
        tenant_id=principal.tenant_id,
        image_id=image.id,
        reservation_key=reservation_key,
        prompt=prompt,
        status="processing",
    )
    session.add(operation)
    ledger = CreditLedgerService(session)
    reservation = ledger.reserve(
        principal.tenant_id,
        resource="image_edit",
        model=container.settings.openai_image_model,
        estimate=estimated_image_charge(container.settings.openai_image_model),
        idempotency_key=reservation_key,
        reference_id=image.id,
    )
    if reservation.status == "settled":
        raise HTTPException(status_code=409, detail="Este tratamento já foi concluído.")
    if reservation.status == "started":
        raise HTTPException(
            status_code=409, detail="Este tratamento está em processamento ou reconciliação."
        )
    ledger.start_reservation(principal.tenant_id, reservation_key)
    image.status = "processing"
    image.optimization_prompt = prompt
    image.error = None
    session.commit()
    heartbeat_stopped = threading.Event()

    def renew_reservation() -> None:
        while not heartbeat_stopped.wait(60):
            with container.database.session_factory() as heartbeat_session:
                CreditLedgerService(heartbeat_session).touch_reservation(
                    principal.tenant_id, reservation_key
                )

    heartbeat_thread = threading.Thread(target=renew_reservation, daemon=True)
    heartbeat_thread.start()
    new_key: str | None = None
    call_accepted = False
    try:
        result = container.ai_provider.edit_image(
            original, filename=image.original_name, prompt=prompt
        )
        call_accepted = True
        output = PropertyImageUpload(
            original_name=image.original_name,
            content_type="image/png",
            content=result.content,
        )
        # A chamada aceita é faturada antes da persistência do artefato. Assim uma
        # falha de storage não libera indevidamente créditos já consumidos.
        ledger.settle_reservation(
            principal.tenant_id,
            idempotency_key=reservation_key,
            charge=image_token_charge(
                container.settings.openai_image_model,
                input_image_tokens=result.input_image_tokens,
                input_text_tokens=result.input_text_tokens,
                output_image_tokens=result.output_image_tokens,
            ),
            model=container.settings.openai_image_model,
            reference_id=image.id,
            extra={"property_id": str(property_id), "image_id": str(image.id)},
        )
        validate_property_image(output, max_bytes=container.settings.property_image_max_bytes)
        new_key = LocalPropertyImageStorage.build_key(
            principal.tenant_id,
            property_id,
            image.id,
            f"derived-{uuid4().hex}",
            output.content_type,
        )
        container.property_image_storage.put(
            principal.tenant_id, new_key, output.content, output.content_type
        )
        old_key = image.derived_storage_key
        image.derived_storage_key = new_key
        image.derived_content_type = output.content_type
        image.derived_size = len(output.content)
        image.status = "ready"
        image.updated_at = datetime.now(UTC)
        operation.status = "ready"
        operation.derived_storage_key = new_key
        operation.completed_at = datetime.now(UTC)
        if old_key:
            session.add(
                PropertyMediaCleanupModel(
                    id=uuid4(), tenant_id=principal.tenant_id, storage_key=old_key
                )
            )
        session.commit()
    except AiProviderRejectedError as exc:
        ledger.release_reservation(principal.tenant_id, reservation_key)
        image.status = "failed"
        image.error = "A OpenAI rejeitou o tratamento solicitado."
        operation.status = "failed"
        operation.error = image.error
        operation.completed_at = datetime.now(UTC)
        session.commit()
        raise HTTPException(status_code=502, detail=image.error) from exc
    except AiProviderDispatchUncertainError as exc:
        image.status = "failed"
        image.error = "Resultado incerto; a reserva aguarda reconciliação."
        operation.status = "uncertain"
        operation.error = image.error
        operation.completed_at = datetime.now(UTC)
        session.commit()
        raise HTTPException(status_code=502, detail=image.error) from exc
    except Exception as exc:
        session.rollback()
        if new_key is not None:
            with container.database.session_factory() as cleanup_session:
                cleanup_session.add(
                    PropertyMediaCleanupModel(
                        id=uuid4(),
                        tenant_id=principal.tenant_id,
                        storage_key=new_key,
                    )
                )
                cleanup_session.commit()
        with container.database.session_factory() as failure_session:
            failed = _image_model(
                failure_session, principal.tenant_id, property_id, image_id
            )
            failed.status = "failed"
            failed.error = f"Falha ao persistir o tratamento: {exc}"[:1000]
            failed_operation = failure_session.get(
                PropertyImageOperationModel, payload.operation_id
            )
            if failed_operation is not None:
                failed_operation.status = "failed" if call_accepted else "uncertain"
                failed_operation.error = failed.error
                failed_operation.completed_at = datetime.now(UTC)
            failure_session.commit()
        raise HTTPException(
            status_code=502,
            detail=(
                "O tratamento foi faturado, mas a imagem derivada não pôde ser persistida."
                if call_accepted
                else "O resultado da chamada é incerto e requer reconciliação."
            ),
        ) from exc
    finally:
        heartbeat_stopped.set()
        heartbeat_thread.join(timeout=2)
    return _linked_image_response(image)
